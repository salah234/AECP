"""Merge policy: explicit per-risk-tier rules for what happens to a
detected conflict.

Some conflicts auto-resolve (e.g. two mechanical-tier formatting changes
with a trivial textual overlap), some block on a human. The rule set is a
lookup table, not inferred behavior, per CLAUDE.md's preference for
boring, inspectable data structures.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conflict import ConflictKind, ConflictReport


@dataclass
class MergePolicyDecision:
    report_id: str
    auto_merge: bool
    requires_human: bool
    rationale: str


# Explicit (risk_tier, conflict_kind) -> policy table. Populated during
# implementation per CLAUDE.md's Escalation Policy; any pair not present
# here must default to requires_human=True, never to auto-merge.
POLICY_TABLE: dict[tuple[str, ConflictKind], str] = {}


class MergePolicyResolver:
    def __init__(self) -> None:
        raise NotImplementedError

    def resolve(self, report: ConflictReport, risk_tier: str) -> MergePolicyDecision:
        """Look up the policy for (risk_tier, report.kind) and return a
        decision. Any risk_tier/kind combination absent from POLICY_TABLE
        must resolve to requires_human=True.
        """
        raise NotImplementedError
