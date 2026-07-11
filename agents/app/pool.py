"""Agent pool capacity management: tracks available worker slots and
backs the AssignmentEngine's spawn requests with real (or simulated, in
dev) compute capacity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PoolCapacity:
    total_slots: int
    in_use_slots: int


class AgentPool:
    def __init__(self, lifecycle_manager) -> None:
        raise NotImplementedError

    async def capacity(self, tenant_id: str) -> PoolCapacity:
        raise NotImplementedError

    async def acquire_slot(self, tenant_id: str) -> bool:
        """Reserve a slot for a new session, or return False if the pool
        is at capacity (caller must leave the task unassigned, not
        overcommit).
        """
        raise NotImplementedError

    async def release_slot(self, tenant_id: str) -> None:
        raise NotImplementedError
