"""Semantic conflict detection: catches cases where two changes are
individually valid but jointly incoherent.

This is the one piece of AECP's own coordination logic that may itself
call out to a model (to reason about whether two diffs' intents conflict)
rather than being a pure structural check — but the decision of what to
do with that judgment (auto-resolve vs. escalate) still goes through
merge_policy.py's explicit, non-model-driven rules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SemanticDiffResult:
    jointly_coherent: bool
    explanation: str


class SemanticDiffer:
    def __init__(self, state_client) -> None:
        raise NotImplementedError

    async def compare(self, tenant_id: str, task_id_a: str, task_id_b: str) -> SemanticDiffResult:
        """Determine whether task_id_a's and task_id_b's changes are
        jointly coherent, using each task's diff plus relevant interface
        contracts and decision log entries from the State Layer.
        """
        raise NotImplementedError
