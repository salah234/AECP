"""gRPC servicer implementation for aecp.observability.v1.AuditService."""

from __future__ import annotations


class AuditServicer:
    """Implements the generated AuditServiceServicer base class
    (see proto/observability/v1/observability.proto).
    """

    def __init__(self, audit_trail) -> None:
        raise NotImplementedError

    async def RecordAuditEvent(self, request, context):
        raise NotImplementedError

    async def QueryAuditEvents(self, request, context):
        raise NotImplementedError


def build_server(servicer: AuditServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
