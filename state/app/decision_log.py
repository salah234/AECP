"""Decision log: why something was built a certain way, not just what.

Append-only by design — decisions are never edited or deleted, only
superseded by a later entry referencing the one it revises. This is what
lets a future agent (or human) understand the reasoning behind existing
code without re-deriving it from scratch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class DecisionLogEntry:
    entry_id: str
    tenant_id: str # Each customer/workspace owns the decision
    task_id: str # Task caused the decision
    summary: str
    rationale: str # Full explaination of said task
    decided_by_kind: str # Who made decision
    decided_by_id: str # Exact person
    decided_at: datetime
    supersedes_entry_id: str | None = None # Person who did decision earlier


class DecisionLog:
    def __init__(self, repository) -> None:
        self.repository = repository

    async def record(self, entry: DecisionLogEntry) -> DecisionLogEntry:
        """Append a new entry. Never mutates or removes an existing one."""
        return await self.repository.insert_decision(entry)

    async def history_for_task(self, task_id: str) -> list[DecisionLogEntry]:
        return await self.repository.get_decisions_by_task(task_id)

    async def history_for_module(self, tenant_id: str, module_path: str) -> list[DecisionLogEntry]:
        return await self.repository.get_decisions_for_module(tenant_id, module_path)
