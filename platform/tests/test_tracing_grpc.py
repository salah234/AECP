from __future__ import annotations

import grpc
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from aecp_platform.tracing_grpc import TracingClientInterceptor, TracingServerInterceptor


@pytest.fixture(scope="module")
def span_exporter():
    """A real TracerProvider wired to an in-memory exporter instead of
    the real OTLP one — verifies actual span creation/propagation
    without a collector.

    Module-scoped and installed exactly once: OpenTelemetry's global
    tracer provider can only be set a single time per process (a second
    set_tracer_provider call is a silent no-op with a warning), and
    tracing_grpc.py's module-level `_tracer` is bound via `get_tracer()`
    at import time as a proxy that resolves to whichever provider
    eventually gets installed — so tests isolate from each other by
    clearing the exporter (see _clear_spans below), not by swapping
    providers per test.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture(autouse=True)
def _clear_spans(span_exporter):
    span_exporter.clear()
    yield


class _FakeClientCallDetails:
    def __init__(self, method: str, metadata: list[tuple[str, str]] | None = None) -> None:
        self.method = method
        self.metadata = metadata or []

    def _replace(self, **kwargs):
        merged = {"method": self.method, "metadata": self.metadata}
        merged.update(kwargs)
        return _FakeClientCallDetails(merged["method"], merged["metadata"])


class _FakeHandlerCallDetails:
    def __init__(self, method: str, invocation_metadata: tuple = ()) -> None:
        self.method = method
        self.invocation_metadata = invocation_metadata


def _fake_handler(behavior):
    return grpc.unary_unary_rpc_method_handler(behavior)


@pytest.mark.asyncio
class TestTracingClientInterceptor:
    async def test_injects_traceparent_into_outgoing_metadata(self, span_exporter) -> None:
        interceptor = TracingClientInterceptor()
        seen_metadata = {}

        async def continuation(details, request):
            seen_metadata["metadata"] = details.metadata
            return "response"

        result = await interceptor.intercept_unary_unary(
            continuation,
            _FakeClientCallDetails("/aecp.coordinator.v1.CoordinatorService/Schedule"),
            "request",
        )

        assert result == "response"
        keys = [key for key, _ in seen_metadata["metadata"]]
        assert "traceparent" in keys

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "/aecp.coordinator.v1.CoordinatorService/Schedule"
        assert spans[0].kind == trace.SpanKind.CLIENT

    async def test_records_exception_and_reraises(self, span_exporter) -> None:
        interceptor = TracingClientInterceptor()

        async def continuation(details, request):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await interceptor.intercept_unary_unary(
                continuation, _FakeClientCallDetails("/svc/Method"), "request"
            )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
class TestTracingServerInterceptor:
    async def test_creates_child_span_from_incoming_traceparent(self, span_exporter) -> None:
        # Produce a real traceparent the way the client interceptor would.
        client_interceptor = TracingClientInterceptor()
        captured = {}

        async def client_continuation(details, request):
            captured["metadata"] = details.metadata
            return "ok"

        await client_interceptor.intercept_unary_unary(
            client_continuation, _FakeClientCallDetails("/svc/Method"), "request"
        )
        client_span = span_exporter.get_finished_spans()[0]

        server_interceptor = TracingServerInterceptor()

        async def behavior(request, context):
            return "server-ok"

        async def server_continuation(handler_call_details):
            return _fake_handler(behavior)

        handler = await server_interceptor.intercept_service(
            server_continuation,
            _FakeHandlerCallDetails("/svc/Method", tuple(captured["metadata"])),
        )
        result = await handler.unary_unary("request", context=None)
        assert result == "server-ok"

        spans = span_exporter.get_finished_spans()
        server_span = spans[-1]
        assert server_span.name == "/svc/Method"
        assert server_span.kind == trace.SpanKind.SERVER
        assert server_span.parent.trace_id == client_span.context.trace_id
        assert server_span.context.trace_id == client_span.context.trace_id

    async def test_passes_through_none_handler(self, span_exporter) -> None:
        server_interceptor = TracingServerInterceptor()

        async def server_continuation(handler_call_details):
            return None

        result = await server_interceptor.intercept_service(
            server_continuation, _FakeHandlerCallDetails("/svc/Unregistered")
        )
        assert result is None
