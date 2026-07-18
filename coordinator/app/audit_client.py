"""Thin gRPC client wrapper around aecp.observability.v1.AuditService.

Every Tier 2+ state change and every auth/authz failure must be written
to the append-only audit trail (CLAUDE.md, Security & Multi-Tenancy).
TradeoffResolver is the primary caller: every escalation decision and
blocker report it makes is Tier 2+ by definition (it is a cross-agent
tradeoff). No shared AuditClient exists anywhere in the repo yet (see
observability/app/audit.py's docstring, which references one that was
never built) — this is Coordinator's own minimal wrapper around the raw
generated stub, not a promotion of that docstring's promise to /platform.

/observability's own servicer is not implemented yet (its build_server
still raises NotImplementedError), so calls here fail with a
transport-level error until that lands. record_audit_event() returns
False on failure instead of raising: a missing audit trail must not be
allowed to block the Tier 2+ decision it is trying to log, but the
failure is always logged loudly, never swallowed silently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import grpc

from app.channels import caller_metadata
from app.common.v1 import common_pb2
from app.observability.v1 import observability_pb2, observability_pb2_grpc

logger = logging.getLogger(__name__)


class AuditClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "coordinator") -> None:
        self._stub = observability_pb2_grpc.AuditServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def record_audit_event(
        self,
        *,
        tenant_id: str,
        actor_kind: "common_pb2.Actor.Kind",
        actor_id: str,
        action: str,
        resource: str,
        security_relevant: bool,
    ) -> bool:
        event = common_pb2.AuditEvent(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            actor=common_pb2.Actor(kind=actor_kind, id=actor_id),
            action=action,
            resource=resource,
            security_relevant=security_relevant,
        )
        event.occurred_at.FromDatetime(datetime.now(timezone.utc))

        try:
            await self._stub.RecordAuditEvent(
                observability_pb2.RecordAuditEventRequest(event=event),
                metadata=self._metadata,
            )
        except grpc.aio.AioRpcError as exc:
            logger.error(
                "AuditService.RecordAuditEvent unavailable (%s); Tier 2+ "
                "event '%s' on '%s' was NOT durably recorded.",
                exc.code(),
                action,
                resource,
            )
            return False
        return True
