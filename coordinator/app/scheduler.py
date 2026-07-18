"""Scheduling: decides what can run in parallel vs. what must be serialized.

Reads ready task nodes from the Task Graph service, checks ownership
boundaries for overlap, and produces a set of assignment requests for the
current tick. Does not itself pick which agent gets a task — that is
assignment.py's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app import ownership

logger = logging.getLogger(__name__)


@dataclass
class ScheduleTick:
    tenant_id: str
    ready_task_ids: list[str]
    parallelizable_task_ids: list[str]
    serialized_task_ids: list[str]


class Scheduler:
    """Consumes ready task nodes and partitions them into parallel vs.
    serialized batches based on ownership boundary overlap.

    Takes an integration_client (not a state_client) rather than the
    tuple originally scaffolded: ownership-overlap partitioning is a
    structural question about *this tick's* candidate set, and
    IntegrationService.DetectConflicts is the Conflict & Integration
    Layer's own answer to "can these run in parallel" (CLAUDE.md's
    Integration Layer section) — the State Layer's decision log/ownership
    map answer a different question (what happened historically) that
    this partitioning step doesn't need. See integration_client.py's
    docstring for why a failed/unimplemented Integration call degrades to
    "no additional conflicts known" rather than blocking the tick.
    """

    def __init__(self, taskgraph_client, integration_client=None) -> None:
        self.taskgraph_client = taskgraph_client
        self.integration_client = integration_client

    async def plan_tick(self, tenant_id: str) -> ScheduleTick:
        """Fetch ready task nodes for tenant_id and partition them into a
        ScheduleTick describing what can be assigned this cycle.
        """
        nodes = await self.taskgraph_client.list_ready_task_nodes(tenant_id)
        ready_task_ids = [node.task_id for node in nodes]

        conflicted_task_ids: set[str] = set()
        if self.integration_client is not None and ready_task_ids:
            reports = await self.integration_client.detect_conflicts(
                tenant_id, ready_task_ids
            )
            if reports:
                for report in reports:
                    conflicted_task_ids.update(report.task_ids)

        parallelizable: list[str] = []
        serialized: list[str] = []
        claimed_nodes: list = []

        for node in nodes:
            if node.task_id in conflicted_task_ids:
                logger.info(
                    "Task %s serialized this tick: Integration reported a conflict.",
                    node.task_id,
                )
                serialized.append(node.task_id)
                continue

            overlaps_claimed = any(
                ownership.boundaries_overlap(node.ownership, claimed.ownership)
                for claimed in claimed_nodes
            )
            if overlaps_claimed:
                serialized.append(node.task_id)
            else:
                parallelizable.append(node.task_id)
                claimed_nodes.append(node)

        return ScheduleTick(
            tenant_id=tenant_id,
            ready_task_ids=ready_task_ids,
            parallelizable_task_ids=parallelizable,
            serialized_task_ids=serialized,
        )

    async def _has_ownership_overlap(
        self, task_id_a: str, task_id_b: str, tenant_id: str
    ) -> bool:
        """Return whether two ready task nodes declare overlapping
        ownership boundaries and therefore cannot run in parallel.
        """
        node_a = await self.taskgraph_client.get_task_node(task_id_a, tenant_id)
        node_b = await self.taskgraph_client.get_task_node(task_id_b, tenant_id)

        if node_a is None or node_b is None:
            raise ValueError(
                f"Cannot compare ownership: unknown task id(s) "
                f"{task_id_a!r}, {task_id_b!r}"
            )

        return ownership.boundaries_overlap(node_a.ownership, node_b.ownership)
