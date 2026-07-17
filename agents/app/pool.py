"""Agent pool capacity management: tracks available worker slots and
backs the AssignmentEngine's spawn requests with real (or simulated, in
dev) compute capacity.

Slot accounting is a plain in-memory counter guarded by a lock rather than
derived by counting LifecycleManager's live session registry on every
call: acquire/release must be atomic with respect to concurrent
SpawnSession/TerminateSession RPCs, and a counter guarded by a single lock
gives that for free, whereas "count active sessions, then decide" is
inherently racy (two concurrent counts can both observe room for one more
slot). reconcile() is provided to resync the counter against the registry
after a restart, since a process restart empties both.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

DEFAULT_MAX_SLOTS_PER_TENANT = 10


@dataclass
class PoolCapacity:
    total_slots: int
    in_use_slots: int


class AgentPool:
    def __init__(
        self,
        lifecycle_manager,
        max_slots_per_tenant: int = DEFAULT_MAX_SLOTS_PER_TENANT,
    ) -> None:
        self.lifecycle_manager = lifecycle_manager
        self.max_slots_per_tenant = max_slots_per_tenant
        self._lock = asyncio.Lock()
        self._in_use: dict[str, int] = defaultdict(int)

    async def capacity(self, tenant_id: str) -> PoolCapacity:
        async with self._lock:
            return PoolCapacity(
                total_slots=self.max_slots_per_tenant,
                in_use_slots=self._in_use[tenant_id],
            )

    async def acquire_slot(self, tenant_id: str) -> bool:
        """Reserve a slot for a new session, or return False if the pool
        is at capacity (caller must leave the task unassigned, not
        overcommit).
        """
        async with self._lock:
            if self._in_use[tenant_id] >= self.max_slots_per_tenant:
                return False
            self._in_use[tenant_id] += 1
            return True

    async def release_slot(self, tenant_id: str) -> None:
        async with self._lock:
            if self._in_use[tenant_id] > 0:
                self._in_use[tenant_id] -= 1

    async def reconcile(self, tenant_id: str) -> PoolCapacity:
        """Resync the in-use counter for `tenant_id` against
        LifecycleManager's live registry. Intended for use at startup, or
        after any code path that might have mutated sessions without going
        through acquire_slot/release_slot.
        """
        active = await self.lifecycle_manager.count_active(tenant_id)
        async with self._lock:
            self._in_use[tenant_id] = active
            return PoolCapacity(
                total_slots=self.max_slots_per_tenant,
                in_use_slots=self._in_use[tenant_id],
            )
