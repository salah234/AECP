"""Assignment: picks which agent (or agent pool slot) takes each ready task.

Grants a risk tier no higher than the task node's own tier. An agent must
never self-assign a higher tier than the task graph gave it; this module
is where that grant is made and recorded, not the agent.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import grpc

from app.common.v1 import common_pb2
from app.statemachine import TASK_STATE_TO_PROTO, TaskState

logger = logging.getLogger(__name__)


@dataclass
class AssignmentDecision:
    task_id: str
    agent_id: str
    granted_risk_tier: int
    rationale: str


class AssignmentEngine:
    """Maps ready, schedulable task nodes to available agent pool
    capacity via the Agent Pool service.

    Takes a taskgraph_client in addition to the originally scaffolded
    agent_pool_client/state_client: granting "no higher than the task
    node's own tier" requires knowing that tier, and building the
    Coordinator-forwarded task_node_snapshot (see
    docs/adr/0007-agent-pool-has-no-taskgraph-edge.md) requires the full
    node — both only TaskGraph can supply.

    There is a window between get_task_node and update_task_status
    (ASSIGNED) during which a second, concurrent Schedule() call on this
    same process (e.g. two ticks overlapping in flight) could read the
    same still-PENDING task and spawn a second agent session for it.
    _claiming closes that window in-process. It does NOT protect against
    the same race across multiple Coordinator replicas — that requires
    TaskGraphService.UpdateTaskStatus (or a dedicated claim RPC) to
    perform a conditional, compare-and-swap update
    (`WHERE status = PENDING`) at the database layer, which
    taskgraph/app/repository.py does not yet implement. Treat this as
    defense in depth for the common single-replica case, not a
    substitute for that follow-up.
    """

    def __init__(self, agent_pool_client, state_client, taskgraph_client) -> None:
        self.agent_pool_client = agent_pool_client
        self.state_client = state_client
        self.taskgraph_client = taskgraph_client
        self._claim_lock = asyncio.Lock()
        self._claiming: set[str] = set()

    async def assign(self, task_ids: list[str], tenant_id: str) -> list[AssignmentDecision]:
        """Produce assignment decisions for the given ready task ids,
        spawning agent sessions as needed via the Agent Pool service.

        A task whose spawn fails (e.g. Agent Pool at capacity) is skipped
        rather than aborting the whole batch, so one exhausted tenant
        doesn't block every other ready task this tick. A task already
        being claimed by a concurrent assign() call is skipped the same
        way (see _claiming above).
        """
        decisions: list[AssignmentDecision] = []

        for task_id in task_ids:
            async with self._claim_lock:
                if task_id in self._claiming:
                    logger.info(
                        "Skipping assignment of task %s this tick: already "
                        "being claimed by a concurrent assign() call.",
                        task_id,
                    )
                    continue
                self._claiming.add(task_id)

            try:
                await self._assign_one(task_id, tenant_id, decisions)
            finally:
                async with self._claim_lock:
                    self._claiming.discard(task_id)

        return decisions

    async def _assign_one(
        self, task_id: str, tenant_id: str, decisions: list[AssignmentDecision]
    ) -> None:
        node = await self.taskgraph_client.get_task_node(task_id, tenant_id)
        if node is None:
            raise ValueError(f"Cannot assign unknown task '{task_id}'")

        if node.status != common_pb2.TASK_STATUS_PENDING:
            # Someone else already acted on this task since it was listed
            # as ready — a concurrent assign() call, or a stale/duplicate
            # task_id passed in twice. _claiming above only protects
            # against two calls racing *before* either has written back;
            # this catches the sequential case where the first call has
            # already completed and moved the task past PENDING.
            logger.info(
                "Skipping assignment of task %s: status is no longer PENDING (%s).",
                task_id,
                common_pb2.TaskStatus.Name(node.status),
            )
            return

        try:
            session = await self.agent_pool_client.spawn_session(
                tenant_id=tenant_id,
                task_id=task_id,
                granted_risk_tier=node.risk_tier,
                ownership=node.ownership,
                task_node_snapshot=node.SerializeToString(),
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "Skipping assignment of task %s this tick: Agent Pool "
                "spawn failed (%s).",
                task_id,
                exc.code(),
            )
            return

        rationale = (
            f"Assigned to agent session {session.session_id} at the task's own "
            f"risk tier ({common_pb2.RiskTier.Name(node.risk_tier)}); an agent must "
            "never self-assign a higher tier than the task graph granted it."
        )

        decisions.append(
            AssignmentDecision(
                task_id=task_id,
                agent_id=session.session_id,
                granted_risk_tier=node.risk_tier,
                rationale=rationale,
            )
        )

        # Push the new status back to TaskGraph so this task drops out
        # of ListReadyTaskNodes next tick — CLAUDE.md's "never let the
        # task graph and the state layer diverge silently".
        await self.taskgraph_client.update_task_status(
            task_id, tenant_id, TASK_STATE_TO_PROTO[TaskState.ASSIGNED], reason=rationale
        )

        try:
            await self.state_client.record_decision(
                tenant_id=tenant_id,
                task_id=task_id,
                summary="Task assigned to an agent session",
                rationale=rationale,
                decided_by_kind=common_pb2.Actor.KIND_COORDINATOR,
                decided_by_id="coordinator",
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "Assignment of task %s succeeded but was not recorded to "
                "the decision log: State unavailable (%s).",
                task_id,
                exc.code(),
            )
