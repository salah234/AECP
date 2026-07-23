"""gRPC client/server interceptors that carry OpenTelemetry trace context
across every internal service edge.

Lives in /platform, unlike the interim per-service AllowListInterceptor
(see agents/app/interceptors.py and friends), because this has no
per-service parameter the way an allow-list does — it is the same code
in every service, which is exactly what /platform exists to hold instead
of seven copies drifting independently (see CLAUDE.md's "every backend
service depends on it instead of reimplementing cross-cutting
concerns"). Every proto RPC in this repo is unary-unary, so only that
call shape is handled here; a future streaming RPC would need its own
interceptor methods added alongside these.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableSequence

import grpc
from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_tracer = trace.get_tracer("aecp.grpc")


class _MetadataSetter:
    """Injects a W3C traceparent header into a plain list of (key, value)
    tuples — grpc's own outgoing metadata shape, not a dict, so
    opentelemetry.propagate's default dict-based carrier doesn't apply.
    """

    def set(self, carrier: MutableSequence[tuple[str, str]], key: str, value: str) -> None:
        carrier.append((key, value))


class _MetadataGetter:
    """Reads a W3C traceparent header back out of grpc's incoming
    invocation_metadata (a sequence of (key, value) tuples, possibly
    None on a call that attaches no metadata at all).
    """

    def get(self, carrier: Iterable[tuple[str, str]] | None, key: str) -> list[str]:
        for existing_key, value in carrier or ():
            if existing_key == key:
                return [value]
        return []

    def keys(self, carrier: Iterable[tuple[str, str]] | None) -> list[str]:
        return [key for key, _ in carrier or ()]


_setter = _MetadataSetter()
_getter = _MetadataGetter()


class TracingClientInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Opens a CLIENT span around every outbound unary call and injects
    its trace context into the call's metadata, so the callee's
    TracingServerInterceptor can continue the same trace rather than
    starting an unrelated one.
    """

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        metadata = list(client_call_details.metadata or [])

        with _tracer.start_as_current_span(
            client_call_details.method, kind=SpanKind.CLIENT
        ) as span:
            propagate.inject(metadata, setter=_setter)
            new_details = client_call_details._replace(metadata=metadata)

            try:
                return await continuation(new_details, request)
            except Exception as exc:  # noqa: BLE001 - re-raised immediately below
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise


class TracingServerInterceptor(grpc.aio.ServerInterceptor):
    """Extracts the caller's trace context (if any) from incoming
    metadata and opens a SERVER span as its child, so this service's work
    shows up in Jaeger as part of the same causal chain the caller
    started rather than a disconnected trace.

    Must be listed before AllowListInterceptor/AllowList.grpc_interceptor
    wherever a server's interceptor chain is built, so even a call that
    gets rejected for an unrecognized caller still produces a span —
    useful for auditing rejected traffic, and consistent with tracing
    being infrastructure that should see everything, not just requests
    that already passed authorization.
    """

    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        parent_context = propagate.extract(
            handler_call_details.invocation_metadata, getter=_getter
        )
        original = handler.unary_unary
        method = handler_call_details.method

        async def _traced(request, context):
            token = otel_context.attach(parent_context)
            try:
                with _tracer.start_as_current_span(method, kind=SpanKind.SERVER) as span:
                    try:
                        return await original(request, context)
                    except Exception as exc:  # noqa: BLE001 - re-raised immediately below
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise
            finally:
                otel_context.detach(token)

        return grpc.unary_unary_rpc_method_handler(
            _traced,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
