from __future__ import annotations

import pytest

from app.risk_tier import can_auto_merge, is_valid_escalation, requires_human_approval
from app.schema import RiskTier


@pytest.mark.parametrize(
    "tier,expected",
    [
        (RiskTier.MECHANICAL, False),
        (RiskTier.LOCAL, False),
        (RiskTier.STRUCTURAL, True),
        (RiskTier.ARCHITECTURAL, True),
    ],
)
def test_requires_human_approval(tier: RiskTier, expected: bool) -> None:
    assert requires_human_approval(tier) is expected


@pytest.mark.parametrize(
    "tier,expected",
    [
        (RiskTier.MECHANICAL, True),
        (RiskTier.LOCAL, False),
        (RiskTier.STRUCTURAL, False),
        (RiskTier.ARCHITECTURAL, False),
    ],
)
def test_can_auto_merge(tier: RiskTier, expected: bool) -> None:
    assert can_auto_merge(tier) is expected


def test_is_valid_escalation_allows_increasing_tier() -> None:
    assert is_valid_escalation(RiskTier.LOCAL, RiskTier.STRUCTURAL) is True
    assert is_valid_escalation(RiskTier.MECHANICAL, RiskTier.ARCHITECTURAL) is True


def test_is_valid_escalation_allows_same_tier() -> None:
    assert is_valid_escalation(RiskTier.LOCAL, RiskTier.LOCAL) is True


def test_is_valid_escalation_rejects_downgrade() -> None:
    assert is_valid_escalation(RiskTier.STRUCTURAL, RiskTier.LOCAL) is False
    assert is_valid_escalation(RiskTier.ARCHITECTURAL, RiskTier.MECHANICAL) is False
