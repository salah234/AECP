"""Consistent OpenTelemetry tracing across every AECP service.

Coordination bugs (a task assigned twice, a conflict missed) are often
only diagnosable by following one causal chain across service boundaries,
so trace context must propagate end to end across every internal gRPC
call and into the audit log.
"""

from __future__ import annotations


def init_tracing(service_name: str, collector_endpoint: str) -> None:
    """Configure the global tracer provider for `service_name`, exporting
    spans via OTLP/gRPC to the collector at `collector_endpoint`
    (see deploy/docker/docker-compose.yml).

    Should be called once at service startup, before any spans are
    created.
    """
    raise NotImplementedError


def shutdown_tracing() -> None:
    """Flush and close the tracer provider. Call on graceful shutdown so
    in-flight spans are not dropped.
    """
    raise NotImplementedError
