"""Conflict detection across candidate task changes.

Three kinds, per CLAUDE.md: textual (overlapping diff hunks), ownership
(touched files outside declared boundary — should be rare if taskgraph
scheduling worked, but checked again here as defense in depth), and
semantic (individually valid, jointly incoherent — e.g. two agents both
"fix" the same invariant in incompatible ways).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConflictKind(Enum):
    TEXTUAL = "textual"
    SEMANTIC = "semantic"
    OWNERSHIP = "ownership"


@dataclass
class ConflictReport:
    report_id: str
    tenant_id: str
    kind: ConflictKind
    task_ids: list[str]
    description: str
    auto_resolvable: bool


class ConflictDetector:
    def __init__(self, taskgraph_client, semantic_diff) -> None:
        raise NotImplementedError

    async def detect(self, tenant_id: str, candidate_task_ids: list[str]) -> list[ConflictReport]:
        """Run textual, ownership, and semantic conflict checks across all
        pairs of candidate task ids and return every report found.
        """
        raise NotImplementedError

    async def _detect_textual(self, task_id_a: str, task_id_b: str) -> ConflictReport | None:
        raise NotImplementedError

    async def _detect_ownership(self, task_id_a: str, task_id_b: str) -> ConflictReport | None:
        raise NotImplementedError
