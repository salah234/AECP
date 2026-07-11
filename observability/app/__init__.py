"""Observability: dashboards, agent activity logs, escalation audit trail.

Owns the append-only audit log every other service writes security- and
escalation-relevant events to, plus the metrics/tracing surface used by
the Grafana dashboards in /observability/dashboards.
"""
