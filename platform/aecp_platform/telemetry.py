"""Consistent OpenTelemetry tracing across every AECP service.

Coordination bugs (a task assigned twice, a conflict missed) are often
only diagnosable by following one causal chain across service boundaries,
so trace context must propagate end to end across every internal gRPC
call and into the audit log. See tracing_grpc.py for the client/server
gRPC interceptors that carry that context across the wire; this module
only owns the tracer provider lifecycle itself.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_provider: TracerProvider | None = None


def init_tracing(service_name: str, collector_endpoint: str) -> None:
    """Configure the global tracer provider for `service_name`, exporting
    spans via OTLP/gRPC to the collector at `collector_endpoint`
    (see deploy/docker/docker-compose.yml).

    Should be called once at service startup, before any spans are
    created. `insecure=True` on the exporter matches every other internal
    edge in local/dev topology (deploy/docker/docker-compose.yml's
    otel-collector has no TLS listener); it is not a statement about
    production, which is out of scope for this module today the same way
    it is for every other service's dev-vs-prod credential handling.
    """
    global _provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=collector_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _provider = provider


def shutdown_tracing() -> None:
    """Flush and close the tracer provider. Call on graceful shutdown so
    in-flight spans are not dropped.

    Safe to call even if init_tracing was never called (e.g. in a test
    process) — becomes a no-op rather than raising, since there is
    nothing to flush.
    """
    global _provider

    if _provider is not None:
        _provider.shutdown()
        _provider = None


def current_trace_id_hex() -> str:
    """Return the 32-hex-character trace id of the currently active span,
    or "" if there is no active span (tracing not initialized, or called
    outside any traced call).

    Used by gateway to hand the dashboard a Jaeger-lookup-able id for the
    request that just triggered a coordination action, e.g. an "invoke an
    agent" call — see gateway/app/routers/coordinator.py.
    """
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return ""

    return format(span_context.trace_id, "032x")
