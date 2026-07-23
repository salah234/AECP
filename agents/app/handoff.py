"""Handoff protocol: transferring an in-progress task to a new agent
session instance without loss of continuity.

Triggered by lifecycle.reap_expired, an explicit agent-requested handoff,
or a Coordinator-directed reassignment. The new session must rehydrate
from the State Layer exactly as a first-time session would — handoff
never copies scratch context directly between sessions.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.v1 import common_pb2
from app.lifecycle import AgentSession


@dataclass
class HandoffRecord:
    old_session_id: str
    new_session_id: str
    reason: str


class HandoffCoordinator:
    def __init__(self, lifecycle_manager, hydrator, state_client, executor=None) -> None:
        self.lifecycle_manager = lifecycle_manager
        self.hydrator = hydrator
        self.state_client = state_client
        self.executor = executor

    async def handoff(self, session_id: str, reason: str) -> AgentSession:
        """Terminate the old session, spawn a replacement session for the
        same task, and record the handoff in the decision log.

        Spawning the replacement happens *before* the decision-log write,
        and a decision-log failure does not fail this call: once
        terminate_and_return has atomically claimed and torn down the old
        session, there is no way back to it (see lifecycle.py's docstring
        on why that claim is atomic) — continuity for the task depends on
        a replacement existing, so restoring it is the critical path.
        Recording *why* is important institutional memory (CLAUDE.md's
        State & Memory Layer), but a State outage must not leave a task
        with no agent session at all, which is a strictly worse failure
        mode than a missing decision-log entry.
        """
        old_session = await self.lifecycle_manager.terminate_and_return(
            session_id, reason=f"handoff: {reason}"
        )
        if old_session is None:
            raise LookupError(f"session '{session_id}' not found")

        boundary = common_pb2.OwnershipBoundary()
        if old_session.ownership_boundary:
            boundary.ParseFromString(old_session.ownership_boundary)

        new_session = await self.lifecycle_manager.spawn(
            tenant_id=old_session.tenant_id,
            task_id=old_session.task_id,
            granted_risk_tier=old_session.granted_risk_tier,
            ownership_globs=list(boundary.path_globs),
            ownership_boundary=old_session.ownership_boundary,
            task_node_snapshot=old_session.task_node_snapshot,
        )

        if self.executor is not None:
            # The old session's execution was already cancelled above —
            # terminate_and_return calls execution_canceller before this
            # method's first line even returns (see lifecycle.py).
            handle = await self.lifecycle_manager.get_sandbox_handle(new_session.session_id)
            if handle is not None:
                self.executor.spawn_background(new_session, handle.scratch_dir)

        try:
            await self.state_client.record_decision(
                tenant_id=old_session.tenant_id,
                task_id=old_session.task_id,
                summary=f"Agent session {session_id} handed off",
                rationale=reason,
                # Actor.Kind has no dedicated "system"/"agent pool" value;
                # AGENT is the closest fit for an infrastructure-initiated
                # handoff record (as opposed to a human or the Coordinator
                # itself).
                decided_by_kind=common_pb2.Actor.Kind.KIND_AGENT,
                decided_by_id=session_id,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort audit write
            # TODO: route through a real logger/metrics once
            # aecp_platform.telemetry is implemented (Tier 3, /platform);
            # for now, don't let a swallowed decision-log failure be
            # completely silent.
            print(
                f"WARNING: handoff of session {session_id} succeeded "
                f"(new session {new_session.session_id}) but recording the "
                f"decision in State failed: {exc!r}"
            )

        return new_session
