"""Risk tier policy: the primary lever for human-in-the-loop cost control.

See CLAUDE.md's Escalation Policy table for the canonical tier
definitions. This module is the single place that decides the default
tier for a newly decomposed task and whether a requested tier change is
permitted without human sign-off.
"""

from __future__ import annotations

from .schema import RiskTier

# There is deliberately no DEFAULT_RISK_TIER: grpc_server.py's
# CreateTaskNode already rejects RISK_TIER_UNSPECIFIED with
# INVALID_ARGUMENT ("risk_tier must be explicitly set; it is the primary
# lever for human-in-the-loop cost control and has no safe default") —
# a default here would silently contradict that enforced policy.

RISK_ORDER = {
    RiskTier.MECHANICAL: 0,
    RiskTier.LOCAL: 1,
    RiskTier.STRUCTURAL: 2,
    RiskTier.ARCHITECTURAL: 3,
}


def requires_human_approval(tier: RiskTier) -> bool:
    """Return whether merging a task at this tier requires human approval
    before merge (tiers STRUCTURAL and ARCHITECTURAL). Used by
    grpc_server.py's CreateTaskNode to authoritatively set
    DefinitionOfDone.requires_human_review_gate from the tier's own
    policy, rather than trusting a caller-supplied value that could
    understate it.
    """
    return tier in (RiskTier.STRUCTURAL, RiskTier.ARCHITECTURAL)


def can_auto_merge(tier: RiskTier) -> bool:
    """Return whether a task at this tier can auto-merge on green CI with
    no human involvement at all (tier MECHANICAL only — distinct from
    "does not require approval": LOCAL doesn't require approval either,
    but still gets async review per CLAUDE.md's table, so it does not
    auto-merge in this stronger sense).

    Not yet called anywhere: TaskGraphService's UpdateTaskStatusRequest
    has no field carrying a "CI passed" / "approved by" signal to gate on
    (see proto/taskgraph/v1/taskgraph.proto) — ready for a future
    merge-gate RPC once that proto gap is closed, rather than forcing a
    speculative call site into today's request shape.
    """
    return tier == RiskTier.MECHANICAL


def is_valid_escalation(current: RiskTier, requested: RiskTier) -> bool:
    """Return whether moving from `current` to `requested` is a valid
    escalation direction (escalations only ever increase tier; an agent
    must halt and re-escalate rather than downgrade itself).

    Not yet called anywhere: risk-tier escalation requests are handled by
    Coordinator's TradeoffResolver (coordinator/app/tradeoff.py), a
    separate deployable with its own Python package — this function can
    only ever be called from within TaskGraphService itself, and no
    TaskGraph RPC currently exposes an "escalate this task's tier" verb
    (TaskNode.risk_tier is set once at CreateTaskNode and never mutated
    by any other RPC). Kept here, tested, and ready for whichever service
    eventually owns that mutation.
    """
    return RISK_ORDER[current] <= RISK_ORDER[requested]
