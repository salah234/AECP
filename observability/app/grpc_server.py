"""gRPC servicer implementation for aecp.observability.v1.AuditService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import grpc
import grpc.aio
from aecp_platform.dbtenant import TenantID, bind_tenant
from aecp_platform.tracing_grpc import TracingServerInterceptor
from grpc_reflection.v1alpha import reflection

from app.audit import AuditEvent
from app.common.v1 import common_pb2
from app.interceptors import AllowListInterceptor
from app.observability.v1 import observability_pb2, observability_pb2_grpc

# "No lower bound" for QueryAuditEvents when the caller leaves `since`
# unset: the query is `occurred_at >= $2` (see repository.py), so any
# timestamp before the very first audit_events row satisfies that
# unconditionally without needing a separate "no filter" code path in
# SQL. Deliberately the Unix epoch, not datetime.min (year 1): asyncpg
# encodes timestamps as a microsecond delta from the Postgres epoch
# (2000-01-01), and year-1 dates overflow that encoding with a bare
# "bad argument type for built-in operation" TypeError — reproduced live
# against a real Postgres container, not a hypothetical.
_EPOCH_FLOOR = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _actor_kind_to_proto(kind: str):
    return common_pb2.Actor.Kind.Value(f"KIND_{kind.upper()}")


def _event_to_proto(event: AuditEvent) -> common_pb2.AuditEvent:
    proto_event = common_pb2.AuditEvent(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        actor=common_pb2.Actor(
            kind=_actor_kind_to_proto(event.actor_kind),
            id=event.actor_id,
        ),
        action=event.action,
        resource=event.resource,
        security_relevant=event.security_relevant,
    )
    proto_event.occurred_at.FromDatetime(event.occurred_at)
    return proto_event


class AuditServicer:
    """Implements the generated AuditServiceServicer base class
    (see proto/observability/v1/observability.proto).
    """

    def __init__(self, audit_trail) -> None:
        self.audit_trail = audit_trail

    async def RecordAuditEvent(self, request, context):
        proto_event = request.event
        bind_tenant(TenantID(proto_event.tenant_id))

        kind_name = common_pb2.Actor.Kind.Name(proto_event.actor.kind)
        if kind_name == "KIND_UNSPECIFIED":
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "event.actor.kind must be explicitly set "
                "(human/agent/coordinator); it is not optional for an "
                "audit record.",
            )

        event = AuditEvent(
            event_id=proto_event.event_id or str(uuid4()),
            tenant_id=proto_event.tenant_id,
            actor_kind=kind_name.removeprefix("KIND_").lower(),
            actor_id=proto_event.actor.id,
            action=proto_event.action,
            resource=proto_event.resource,
            security_relevant=proto_event.security_relevant,
            occurred_at=(
                proto_event.occurred_at.ToDatetime(tzinfo=timezone.utc)
                if proto_event.HasField("occurred_at")
                else datetime.now(timezone.utc)
            ),
        )

        recorded = await self.audit_trail.record(event)

        return observability_pb2.RecordAuditEventResponse(event_id=recorded.event_id)

    async def QueryAuditEvents(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        bind_tenant(TenantID(request.tenant_id))

        since = (
            request.since.ToDatetime(tzinfo=timezone.utc)
            if request.HasField("since")
            else _EPOCH_FLOOR
        )

        events = await self.audit_trail.query(
            request.tenant_id,
            since,
            request.security_relevant_only,
        )

        return observability_pb2.QueryAuditEventsResponse(
            events=[_event_to_proto(event) for event in events]
        )


@dataclass(frozen=True)
class MTLSConfig:
    certificate_chain: bytes
    private_key: bytes
    ca_certificate: bytes

    @classmethod
    def from_files(cls, *, cert_file: str, key_file: str, ca_file: str) -> "MTLSConfig":
        return cls(
            certificate_chain=Path(cert_file).read_bytes(),
            private_key=Path(key_file).read_bytes(),
            ca_certificate=Path(ca_file).read_bytes(),
        )


def build_server(
    servicer: AuditServicer,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
    allow_list,
    port: int = 50056,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    server = grpc.aio.server(
        interceptors=[TracingServerInterceptor(), AllowListInterceptor(allow_list)]
    )

    observability_pb2_grpc.add_AuditServiceServicer_to_server(servicer, server)

    service_names = (
        observability_pb2.DESCRIPTOR.services_by_name["AuditService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    if mtls_cert_file and mtls_key_file and mtls_ca_file:
        mtls_config = MTLSConfig.from_files(
            cert_file=mtls_cert_file,
            key_file=mtls_key_file,
            ca_file=mtls_ca_file,
        )

        credentials = grpc.ssl_server_credentials(
            [(mtls_config.private_key, mtls_config.certificate_chain)],
            root_certificates=mtls_config.ca_certificate,
            require_client_auth=True,
        )

        server.add_secure_port(f"[::]:{port}", credentials)
    else:
        server.add_insecure_port(f"[::]:{port}")

    return server
