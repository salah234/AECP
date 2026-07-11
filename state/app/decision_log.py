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
    tenant_id: str
    task_id: str
    summary: str
    rationale: str
    decided_by_kind: str
    decided_by_id: str
    decided_at: datetime
    supersedes_entry_id: str | None = None


class DecisionLog:
    def __init__(self, repository) -> None:
        raise NotImplementedError

    async def record(self, entry: DecisionLogEntry) -> DecisionLogEntry:
        """Append a new entry. Never mutates or removes an existing one."""
        raise NotImplementedError

    async def history_for_task(self, task_id: str) -> list[DecisionLogEntry]:
        raise NotImplementedError

    async def history_for_module(self, tenant_id: str, module_path: str) -> list[DecisionLogEntry]:
        raise NotImplementedError
