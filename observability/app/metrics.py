"""Prometheus metrics: sprint/agent-pool health signals surfaced on
Grafana dashboards in /observability/dashboards.

Engineering metrics from CLAUDE.md's scope: sprint velocity, agent
utilization, task completion, build success rate, cycle time, review
latency, technical debt (drift report count). This module implements the
three series observability/dashboards/agent_pool_health.json's own
description already names as expected: task_completion_total,
escalation_total, conflict_detected_total — one Counter per
observability/app/grpc_server.py/coordinator call site
(record_task_completed / record_escalation / record_conflict_detected).
Each carries a tenant_id label (every metric in a multi-tenant system
must be sliceable per tenant) plus the one additional dimension that
matters for that event: risk_tier for completions/escalations (Tier is
the primary human-in-the-loop cost lever per CLAUDE.md's Escalation
Policy), approved for escalations, and kind/auto_resolved for conflicts.
"""

from __future__ import annotations

from prometheus_client import Counter

_task_completion_total: Counter | None = None
_escalation_total: Counter | None = None
_conflict_detected_total: Counter | None = None


def register_metrics() -> None:
    """Register the Prometheus Counter objects this service exposes at
    /metrics.

    Idempotent by design: prometheus_client's default CollectorRegistry
    raises ValueError("Duplicated timeseries in CollectorRegistry") if a
    metric name is registered twice in the same process, which happens
    easily under pytest re-importing/re-invoking this module across test
    files. Guarding on "already registered" here means every call site
    (main.py's startup path, each record_* function, tests) can call this
    unconditionally without knowing about that gotcha or needing to pass
    around a fresh CollectorRegistry per test.
    """
    global _task_completion_total, _escalation_total, _conflict_detected_total

    if _task_completion_total is not None:
        return

    _task_completion_total = Counter(
        "task_completion_total",
        "Total number of task nodes that reached DONE status.",
        ["tenant_id", "risk_tier"],
    )
    _escalation_total = Counter(
        "escalation_total",
        "Total number of Tier 2+ escalations raised to a human for approval.",
        ["tenant_id", "risk_tier", "approved"],
    )
    _conflict_detected_total = Counter(
        "conflict_detected_total",
        "Total number of semantic or ownership conflicts detected between "
        "concurrent agents.",
        ["tenant_id", "kind", "auto_resolved"],
    )


def record_task_completed(tenant_id: str, risk_tier: str) -> None:
    register_metrics()
    assert _task_completion_total is not None
    _task_completion_total.labels(tenant_id=tenant_id, risk_tier=risk_tier).inc()


def record_escalation(tenant_id: str, risk_tier: str, approved: bool) -> None:
    register_metrics()
    assert _escalation_total is not None
    _escalation_total.labels(
        tenant_id=tenant_id, risk_tier=risk_tier, approved=str(approved)
    ).inc()


def record_conflict_detected(tenant_id: str, kind: str, auto_resolved: bool) -> None:
    register_metrics()
    assert _conflict_detected_total is not None
    _conflict_detected_total.labels(
        tenant_id=tenant_id, kind=kind, auto_resolved=str(auto_resolved)
    ).inc()
