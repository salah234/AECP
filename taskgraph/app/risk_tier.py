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


def requires_human_approval(tier: RiskTier) -> bool:
    """Return whether merging a task at this tier requires human approval
    before merge (tiers STRUCTURAL and ARCHITECTURAL).
    """
    raise NotImplementedError


def can_auto_merge(tier: RiskTier) -> bool:
    """Return whether a task at this tier can auto-merge on green CI
    (tier MECHANICAL only).
    """
    raise NotImplementedError


def is_valid_escalation(current: RiskTier, requested: RiskTier) -> bool:
    """Return whether moving from `current` to `requested` is a valid
    escalation direction (escalations only ever increase tier; an agent
    must halt and re-escalate rather than downgrade itself).
    """
    raise NotImplementedError
