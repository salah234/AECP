"""Scheduling: decides what can run in parallel vs. what must be serialized.

Reads ready task nodes from the Task Graph service, checks ownership
boundaries for overlap, and produces a set of assignment requests for the
current tick. Does not itself pick which agent gets a task — that is
assignment.py's job.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScheduleTick:
    tenant_id: str
    ready_task_ids: list[str]
    parallelizable_task_ids: list[str]
    serialized_task_ids: list[str]


class Scheduler:
    """Consumes ready task nodes and partitions them into parallel vs.
    serialized batches based on ownership boundary overlap.
    """

    def __init__(self, taskgraph_client, state_client) -> None:
        raise NotImplementedError

    async def plan_tick(self, tenant_id: str) -> ScheduleTick:
        """Fetch ready task nodes for tenant_id and partition them into a
        ScheduleTick describing what can be assigned this cycle.
        """
        raise NotImplementedError

    async def _has_ownership_overlap(self, task_id_a: str, task_id_b: str) -> bool:
        """Return whether two ready task nodes declare overlapping
        ownership boundaries and therefore cannot run in parallel.
        """
        raise NotImplementedError
