"""Tests for merge_policy.py's POLICY_TABLE lookups and fallback."""

from __future__ import annotations

from datetime import datetime, timezone

from app.common.v1 import common_pb2
from app.conflict import ConflictKind, ConflictReport
from app.merge_policy import MergePolicyResolver


def _make_report(kind: ConflictKind, auto_resolvable: bool = False) -> ConflictReport:
    return ConflictReport(
        report_id="report-1",
        tenant_id="tenant-1",
        kind=kind,
        task_ids=["task-a", "task-b"],
        description="test report",
        auto_resolvable=auto_resolvable,
        detected_at=datetime.now(timezone.utc),
    )


def test_mechanical_textual_auto_merges_when_auto_resolvable() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.TEXTUAL, auto_resolvable=True)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_MECHANICAL)

    assert decision.auto_merge is True
    assert decision.requires_human is False
    assert decision.report_id == "report-1"


def test_mechanical_textual_requires_human_when_not_auto_resolvable() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.TEXTUAL, auto_resolvable=False)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_MECHANICAL)

    assert decision.auto_merge is False
    assert decision.requires_human is True


def test_mechanical_ownership_always_requires_human() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.OWNERSHIP, auto_resolvable=True)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_MECHANICAL)

    assert decision.auto_merge is False
    assert decision.requires_human is True


def test_mechanical_semantic_always_requires_human() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.SEMANTIC, auto_resolvable=True)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_MECHANICAL)

    assert decision.auto_merge is False
    assert decision.requires_human is True


def test_local_textual_requires_human() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.TEXTUAL, auto_resolvable=True)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_LOCAL)

    # Only Mechanical-tier textual overlaps auto-merge, never Local.
    assert decision.auto_merge is False
    assert decision.requires_human is True


def test_structural_tier_always_requires_human_regardless_of_kind() -> None:
    resolver = MergePolicyResolver()

    for kind in ConflictKind:
        report = _make_report(kind, auto_resolvable=True)
        decision = resolver.resolve(report, common_pb2.RISK_TIER_STRUCTURAL)
        assert decision.auto_merge is False, kind
        assert decision.requires_human is True, kind


def test_architectural_tier_always_requires_human_regardless_of_kind() -> None:
    resolver = MergePolicyResolver()

    for kind in ConflictKind:
        report = _make_report(kind, auto_resolvable=True)
        decision = resolver.resolve(report, common_pb2.RISK_TIER_ARCHITECTURAL)
        assert decision.auto_merge is False, kind
        assert decision.requires_human is True, kind


def test_unspecified_risk_tier_falls_back_to_requires_human() -> None:
    resolver = MergePolicyResolver()
    report = _make_report(ConflictKind.TEXTUAL, auto_resolvable=True)

    decision = resolver.resolve(report, common_pb2.RISK_TIER_UNSPECIFIED)

    assert decision.auto_merge is False
    assert decision.requires_human is True


def test_every_entry_has_a_nonempty_rationale() -> None:
    from app.merge_policy import POLICY_TABLE

    for rule in POLICY_TABLE.values():
        assert rule.rationale
