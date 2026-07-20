"""Merge policy: explicit per-risk-tier rules for what happens to a
detected conflict.

Some conflicts auto-resolve (e.g. two mechanical-tier formatting changes
with a trivial textual overlap), some block on a human. The rule set is a
lookup table, not inferred behavior, per CLAUDE.md's preference for
boring, inspectable data structures.

The table below is sourced directly from CLAUDE.md's Escalation Policy
(Risk Tiers) table:

    | Tier | Human involvement                                |
    |------|---------------------------------------------------|
    | 0 Mechanical    | None; auto-merge on green CI              |
    | 1 Local         | Async review, no blocking                 |
    | 2 Structural    | Human approval required before merge       |
    | 3 Architectural | Human-authored task only; agents may       |
    |                 | propose, never merge                       |

Translated into (risk_tier, conflict_kind) policy:

- Only a MECHANICAL-tier TEXTUAL conflict can ever auto-merge, and only
  when the report itself was flagged auto_resolvable=True by the
  detector — a trivial, non-substantive overlap (e.g. two formatting-only
  hunks). MECHANICAL tier alone is not sufficient; the detector's own
  auto_resolvable judgment must agree too.
- OWNERSHIP and SEMANTIC conflicts always require a human, at every
  tier — these represent a real coordination failure (two agents
  actually clobbering each other's work or contradicting an invariant),
  not a trivial overlap a green CI run can wave through. Tier 1's "async
  review, no blocking" is *review*, not *auto-merge*; this table only
  has a binary auto_merge/requires_human distinction, so it resolves to
  requires_human=True for consistency with Tier 2/3 (never silently
  auto-merges a real conflict just because CI is green).
- STRUCTURAL and ARCHITECTURAL tiers always require a human, regardless
  of conflict kind — matching coordinator/app/tradeoff.py's
  _HUMAN_REQUIRED_TIERS precedent for RISK_TIER_STRUCTURAL and
  RISK_TIER_ARCHITECTURAL.
- Any (risk_tier, kind) pair absent from the table (including
  RISK_TIER_UNSPECIFIED) resolves to requires_human=True, auto_merge=False.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.v1 import common_pb2

from .conflict import ConflictKind, ConflictReport


@dataclass
class MergePolicyDecision:
    report_id: str
    auto_merge: bool
    requires_human: bool
    rationale: str


@dataclass(frozen=True)
class _PolicyRule:
    auto_merge: bool
    requires_human: bool
    rationale: str
    # True only for the single (MECHANICAL, TEXTUAL) case: the rule's
    # auto_merge/requires_human values above apply only if the report's
    # own auto_resolvable flag also agrees; otherwise resolve() falls
    # back to requires_human=True regardless of what's written here.
    conditional_on_auto_resolvable: bool = False


_MECHANICAL = common_pb2.RISK_TIER_MECHANICAL
_LOCAL = common_pb2.RISK_TIER_LOCAL
_STRUCTURAL = common_pb2.RISK_TIER_STRUCTURAL
_ARCHITECTURAL = common_pb2.RISK_TIER_ARCHITECTURAL

_HUMAN_REQUIRED_RATIONALE_OWNERSHIP = (
    "Ownership conflicts represent a real coordination failure (two tasks' "
    "declared boundaries overlap), not a trivial overlap CI can wave "
    "through; per CLAUDE.md's Escalation Policy this always requires human "
    "review regardless of risk tier."
)
_HUMAN_REQUIRED_RATIONALE_SEMANTIC = (
    "Semantic conflicts mean two individually valid changes are jointly "
    "incoherent; per CLAUDE.md's Escalation Policy this always requires "
    "human review regardless of risk tier."
)
_HUMAN_REQUIRED_RATIONALE_HIGH_TIER = (
    "Structural and Architectural tier work requires human approval before "
    "merge (Architectural: human-authored only, agents may propose but "
    "never merge) regardless of conflict kind, per CLAUDE.md's Escalation "
    "Policy."
)

# Explicit (risk_tier, conflict_kind) -> policy table. Any pair not
# present here must default to requires_human=True, never to auto-merge
# (see resolve()'s fallback below).
POLICY_TABLE: dict[tuple["common_pb2.RiskTier", ConflictKind], _PolicyRule] = {
    (_MECHANICAL, ConflictKind.TEXTUAL): _PolicyRule(
        auto_merge=True,
        requires_human=False,
        rationale=(
            "Mechanical-tier work auto-merges on green CI per CLAUDE.md's "
            "Escalation Policy; a textual overlap the detector itself "
            "flagged auto_resolvable is trivial enough (e.g. non-"
            "substantive formatting) to not need a human gate."
        ),
        conditional_on_auto_resolvable=True,
    ),
    (_MECHANICAL, ConflictKind.OWNERSHIP): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_OWNERSHIP,
    ),
    (_MECHANICAL, ConflictKind.SEMANTIC): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_SEMANTIC,
    ),
    (_LOCAL, ConflictKind.TEXTUAL): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=(
            "Local-tier work only gets async, non-blocking review when "
            "there's no detected conflict; a textual overlap at this tier "
            "still requires a human to look at before merge (only "
            "Mechanical-tier auto-resolvable overlaps skip that gate)."
        ),
    ),
    (_LOCAL, ConflictKind.OWNERSHIP): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_OWNERSHIP,
    ),
    (_LOCAL, ConflictKind.SEMANTIC): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_SEMANTIC,
    ),
    (_STRUCTURAL, ConflictKind.TEXTUAL): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
    (_STRUCTURAL, ConflictKind.OWNERSHIP): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
    (_STRUCTURAL, ConflictKind.SEMANTIC): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
    (_ARCHITECTURAL, ConflictKind.TEXTUAL): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
    (_ARCHITECTURAL, ConflictKind.OWNERSHIP): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
    (_ARCHITECTURAL, ConflictKind.SEMANTIC): _PolicyRule(
        auto_merge=False,
        requires_human=True,
        rationale=_HUMAN_REQUIRED_RATIONALE_HIGH_TIER,
    ),
}

_DEFAULT_RATIONALE = (
    "No explicit merge policy is defined for this (risk_tier, conflict_kind) "
    "combination; per this table's own fallback rule, an undefined "
    "combination must never be waved through automatically."
)


class MergePolicyResolver:
    def __init__(self) -> None:
        pass

    def resolve(self, report: ConflictReport, risk_tier: "common_pb2.RiskTier") -> MergePolicyDecision:
        """Look up the policy for (risk_tier, report.kind) and return a
        decision. Any risk_tier/kind combination absent from POLICY_TABLE
        must resolve to requires_human=True.
        """
        rule = POLICY_TABLE.get((risk_tier, report.kind))

        if rule is None:
            return MergePolicyDecision(
                report_id=report.report_id,
                auto_merge=False,
                requires_human=True,
                rationale=_DEFAULT_RATIONALE,
            )

        if rule.conditional_on_auto_resolvable and not report.auto_resolvable:
            return MergePolicyDecision(
                report_id=report.report_id,
                auto_merge=False,
                requires_human=True,
                rationale=(
                    "Mechanical-tier textual conflict, but the detector did "
                    "not flag this report auto_resolvable; falling back to "
                    "human review rather than assuming it's trivial."
                ),
            )

        return MergePolicyDecision(
            report_id=report.report_id,
            auto_merge=rule.auto_merge,
            requires_human=rule.requires_human,
            rationale=rule.rationale,
        )
