"""Cross-agent tradeoff resolution and escalation handling.

Handles the Escalate RPC: an agent that discovers a task is bigger than
its granted risk tier halts and calls this instead of proceeding on its
own judgment. This module decides whether to auto-approve a tier bump
(never above what the task graph's own policy allows) or to route to a
human via the observability escalation queue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import grpc

from app.common.v1 import common_pb2
from app.statemachine import TASK_STATE_TO_PROTO, TaskState

logger = logging.getLogger(__name__)

# Escalation Policy (CLAUDE.md): tiers requiring human approval before
# merge can never have their *escalation into* auto-approved either — an
# agent halting because it needs Structural/Architectural trust always
# routes to a human, never gets waved through by Coordinator code alone.
_HUMAN_REQUIRED_TIERS = frozenset(
    {common_pb2.RISK_TIER_STRUCTURAL, common_pb2.RISK_TIER_ARCHITECTURAL}
)


@dataclass
class EscalationDecision:
    task_id: str
    approved: bool
    decided_by: str


class TradeoffResolver:
    """Owns cross-agent tradeoff decisions: escalations, blocker
    reports, and any judgment call that would otherwise require two
    agents to coordinate directly.

    Takes a taskgraph_client in addition to the originally scaffolded
    state_client/observability_client, to push status transitions back to
    TaskGraph and to validate a task exists. EscalateRequest and
    ReportBlockerRequest (proto/coordinator/v1/coordinator.proto) now
    carry tenant_id directly (the calling agent session already knows its
    own tenant), so escalate()/report_blocker() take it as an explicit
    parameter rather than trying to derive it from an unscoped
    GetTaskNode call — TaskGraph's GetTaskNode/UpdateTaskStatus/
    ValidateOwnership all require a bound tenant themselves now (see
    taskgraph/app/grpc_server.py), so there is no tenant-free lookup to
    fall back on.
    """

    def __init__(self, state_client, observability_client, taskgraph_client) -> None:
        self.state_client = state_client
        self.observability_client = observability_client
        self.taskgraph_client = taskgraph_client

    async def escalate(
        self,
        task_id: str,
        tenant_id: str,
        agent_id: str,
        reason: str,
        requested_risk_tier: int,
    ) -> EscalationDecision:
        """Decide whether a requested risk-tier bump can be auto-approved
        or must block on a human reviewer.
        """
        if requested_risk_tier == common_pb2.RISK_TIER_UNSPECIFIED:
            raise ValueError(
                "requested_risk_tier must be explicitly set; it is the primary "
                "lever for human-in-the-loop cost control and has no safe default."
            )

        node = await self.taskgraph_client.get_task_node(task_id, tenant_id)
        if node is None:
            raise ValueError(f"Cannot escalate unknown task '{task_id}'")

        auto_approved = requested_risk_tier not in _HUMAN_REQUIRED_TIERS
        decision = EscalationDecision(
            task_id=task_id,
            approved=auto_approved,
            decided_by="coordinator" if auto_approved else "human",
        )

        tier_name = common_pb2.RiskTier.Name(requested_risk_tier)
        outcome = "auto-approved" if auto_approved else "routed to human review"
        rationale = (
            f"Agent session {agent_id} requested risk tier {tier_name} on task "
            f"{task_id} ({reason}); {outcome} per the Escalation Policy tier table."
        )

        # Escalation attempts are a named security control (see
        # security/THREAT_MODEL.md threat #3: "agent self-escalating
        # beyond its granted risk tier"), so every attempt is audited —
        # approved or not, since a denied attempt is exactly the signal
        # that mitigation exists to catch.
        await self._audit(
            tenant_id=tenant_id,
            actor_id=agent_id,
            action="escalate",
            resource=f"task:{task_id}",
            security_relevant=True,
        )
        await self._record_decision(
            tenant_id=tenant_id,
            task_id=task_id,
            summary=f"Escalation {outcome}",
            rationale=rationale,
            decided_by_kind=common_pb2.Actor.KIND_COORDINATOR,
            decided_by_id=decision.decided_by,
        )

        if auto_approved:
            new_state = TaskState.IN_PROGRESS
        else:
            new_state = TaskState.ESCALATED
        await self.taskgraph_client.update_task_status(
            task_id, tenant_id, TASK_STATE_TO_PROTO[new_state], reason=rationale
        )

        return decision

    async def report_blocker(
        self, task_id: str, tenant_id: str, agent_id: str, description: str
    ) -> None:
        """Record a blocker report and determine whether it changes
        scheduling for dependent task nodes.

        No explicit "cascade block to dependents" call is needed:
        TaskGraph.ready_nodes already requires every dependency to be
        TASK_STATUS_DONE, so marking this task BLOCKED (not DONE) already
        keeps anything depending on it out of the ready set.
        """
        node = await self.taskgraph_client.get_task_node(task_id, tenant_id)
        if node is None:
            raise ValueError(f"Cannot report a blocker for unknown task '{task_id}'")

        await self.taskgraph_client.update_task_status(
            task_id, tenant_id, TASK_STATE_TO_PROTO[TaskState.BLOCKED], reason=description
        )

        await self._audit(
            tenant_id=tenant_id,
            actor_id=agent_id,
            action="report_blocker",
            resource=f"task:{task_id}",
            security_relevant=False,
        )
        await self._record_decision(
            tenant_id=tenant_id,
            task_id=task_id,
            summary="Task blocked",
            rationale=description,
            decided_by_kind=common_pb2.Actor.KIND_AGENT,
            decided_by_id=agent_id,
        )

    async def report_completion(
        self, task_id: str, tenant_id: str, agent_id: str, summary: str, rationale: str
    ) -> None:
        """Record a task's completion and move it into human review.

        Transitions to TASK_STATUS_IN_REVIEW, not TASK_STATUS_DONE: every
        risk tier in CLAUDE.md's Escalation Policy implies some review
        checkpoint before a task is truly finished, and this repo has no
        CI-merge-gate integration yet that could safely auto-promote
        straight to DONE. statemachine.py already models
        IN_PROGRESS--complete-->IN_REVIEW and IN_REVIEW--approve-->DONE
        for whoever/whatever approves it next.
        """
        node = await self.taskgraph_client.get_task_node(task_id, tenant_id)
        if node is None:
            raise ValueError(f"Cannot report completion for unknown task '{task_id}'")

        await self.taskgraph_client.update_task_status(
            task_id, tenant_id, TASK_STATE_TO_PROTO[TaskState.IN_REVIEW], reason=rationale
        )

        await self._audit(
            tenant_id=tenant_id,
            actor_id=agent_id,
            action="report_completion",
            resource=f"task:{task_id}",
            security_relevant=False,
        )
        await self._record_decision(
            tenant_id=tenant_id,
            task_id=task_id,
            summary=summary or "Task completed",
            rationale=rationale,
            decided_by_kind=common_pb2.Actor.KIND_AGENT,
            decided_by_id=agent_id,
        )

    async def _audit(
        self, *, tenant_id: str, actor_id: str, action: str, resource: str, security_relevant: bool
    ) -> None:
        await self.observability_client.record_audit_event(
            tenant_id=tenant_id,
            actor_kind=common_pb2.Actor.KIND_COORDINATOR,
            actor_id=actor_id,
            action=action,
            resource=resource,
            security_relevant=security_relevant,
        )

    async def _record_decision(
        self,
        *,
        tenant_id: str,
        task_id: str,
        summary: str,
        rationale: str,
        decided_by_kind,
        decided_by_id: str,
    ) -> None:
        try:
            await self.state_client.record_decision(
                tenant_id=tenant_id,
                task_id=task_id,
                summary=summary,
                rationale=rationale,
                decided_by_kind=decided_by_kind,
                decided_by_id=decided_by_id,
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "'%s' for task %s succeeded but was not recorded to the "
                "decision log: State unavailable (%s).",
                summary,
                task_id,
                exc.code(),
            )
