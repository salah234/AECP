"""Risk tier policy: the primary lever for human-in-the-loop cost control.

See CLAUDE.md's Escalation Policy table for the canonical tier
definitions. This module is the single place that decides the default
tier for a newly decomposed task and whether a requested tier change is
permitted without human sign-off.
"""

from __future__ import annotations

from .schema import RiskTier

# Default tier assigned when a task's decomposition does not explicitly
# set one. Filled in during implementation per CLAUDE.md's table.
DEFAULT_RISK_TIER: RiskTier | None = None

RISK_ORDER = {
    RiskTier.MECHANICAL: 0,
    RiskTier.LOCAL: 1,
    RiskTier.STRUCTURAL: 2,
    RiskTier.ARCHITECTURAL: 3,
}

def requires_human_approval(tier: RiskTier) -> bool:
    """Return whether merging a task at this tier requires human approval
    before merge (tiers STRUCTURAL and ARCHITECTURAL).
    """
    return tier in (RiskTier.STRUCTURAL, RiskTier.ARCHITECTURAL)
    


def can_auto_merge(tier: RiskTier) -> bool:
    """Return whether a task at this tier can auto-merge on green CI
    (tier MECHANICAL only).
    """
    return tier in (RiskTier.MECHANICAL)


def is_valid_escalation(current: RiskTier, requested: RiskTier) -> bool:
    """Return whether moving from `current` to `requested` is a valid
    escalation direction (escalations only ever increase tier; an agent
    must halt and re-escalate rather than downgrade itself).
    """

    return RISK_ORDER[current] <= RISK_ORDER[requested]
