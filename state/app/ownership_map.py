"""Ownership map: which agent/task last touched which module and why.

Distinct from taskgraph.ownership (which validates a boundary a task is
*allowed* to touch) — this is the historical record of what was *actually*
touched, used by the drift detector and by humans auditing agent activity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC


@dataclass
class OwnershipRecord:
    tenant_id: str
    module_path: str
    last_task_id: str
    last_agent_id: str
    last_touched_at: datetime


class OwnershipMap:
    def __init__(self, repository) -> None:
        self.repository = repository

    async def record_touch(self, tenant_id: str, module_path: str, task_id: str, agent_id: str) -> None:
        record = OwnershipRecord(
            tenant_id=tenant_id,
            module_path=module_path,
            last_task_id=task_id,
            last_agent_id=agent_id,
            last_touched_at=datetime.now(UTC)
        )
        await self.repository.upsert_ownership(record)

    async def get(self, tenant_id: str, module_path: str) -> OwnershipRecord | None:
        return await self.repository.get_ownership(tenant_id, module_path)
