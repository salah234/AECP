"""Prometheus metrics: sprint/agent-pool health signals surfaced on
Grafana dashboards in /observability/dashboards.

Engineering metrics from CLAUDE.md's scope: sprint velocity, agent
utilization, task completion, build success rate, cycle time, review
latency, technical debt (drift report count).
"""

from __future__ import annotations


def register_metrics() -> None:
    """Register the Prometheus Counter/Gauge/Histogram objects this
    service exposes at /metrics.
    """
    raise NotImplementedError


def record_task_completed(tenant_id: str, risk_tier: str) -> None:
    raise NotImplementedError


def record_escalation(tenant_id: str, risk_tier: str, approved: bool) -> None:
    raise NotImplementedError


def record_conflict_detected(tenant_id: str, kind: str, auto_resolved: bool) -> None:
    raise NotImplementedError
