"""Unit tests for metrics.py's Prometheus Counters.

Verifies real prometheus_client registration/inspection (via
prometheus_client.REGISTRY.get_sample_value), not mocks, and that
repeated register_metrics() calls across tests never raise
"Duplicated timeseries in CollectorRegistry" (see metrics.py's
docstring for why that guard exists).
"""

from __future__ import annotations

from prometheus_client import REGISTRY

from app import metrics


def test_register_metrics_is_idempotent() -> None:
    metrics.register_metrics()
    metrics.register_metrics()
    metrics.register_metrics()


def test_record_task_completed_increments_labeled_counter() -> None:
    metrics.register_metrics()
    before = (
        REGISTRY.get_sample_value(
            "task_completion_total",
            {"tenant_id": "tenant-metrics-1", "risk_tier": "local"},
        )
        or 0.0
    )

    metrics.record_task_completed("tenant-metrics-1", "local")

    after = REGISTRY.get_sample_value(
        "task_completion_total",
        {"tenant_id": "tenant-metrics-1", "risk_tier": "local"},
    )
    assert after == before + 1.0


def test_record_escalation_increments_labeled_counter() -> None:
    metrics.register_metrics()
    before = (
        REGISTRY.get_sample_value(
            "escalation_total",
            {
                "tenant_id": "tenant-metrics-2",
                "risk_tier": "structural",
                "approved": "True",
            },
        )
        or 0.0
    )

    metrics.record_escalation("tenant-metrics-2", "structural", True)

    after = REGISTRY.get_sample_value(
        "escalation_total",
        {
            "tenant_id": "tenant-metrics-2",
            "risk_tier": "structural",
            "approved": "True",
        },
    )
    assert after == before + 1.0


def test_record_escalation_distinguishes_approved_and_denied() -> None:
    metrics.register_metrics()
    metrics.record_escalation("tenant-metrics-3", "architectural", False)

    denied = REGISTRY.get_sample_value(
        "escalation_total",
        {
            "tenant_id": "tenant-metrics-3",
            "risk_tier": "architectural",
            "approved": "False",
        },
    )
    approved = REGISTRY.get_sample_value(
        "escalation_total",
        {
            "tenant_id": "tenant-metrics-3",
            "risk_tier": "architectural",
            "approved": "True",
        },
    )
    assert denied == 1.0
    assert approved is None


def test_record_conflict_detected_increments_labeled_counter() -> None:
    metrics.register_metrics()
    before = (
        REGISTRY.get_sample_value(
            "conflict_detected_total",
            {
                "tenant_id": "tenant-metrics-4",
                "kind": "ownership",
                "auto_resolved": "False",
            },
        )
        or 0.0
    )

    metrics.record_conflict_detected("tenant-metrics-4", "ownership", False)

    after = REGISTRY.get_sample_value(
        "conflict_detected_total",
        {
            "tenant_id": "tenant-metrics-4",
            "kind": "ownership",
            "auto_resolved": "False",
        },
    )
    assert after == before + 1.0
