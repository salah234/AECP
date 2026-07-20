"""Shared FastAPI dependency wiring authentication, tenant resolution,
and rate limiting for every router in app/routers/.

Every 401/403 raised here is a security-relevant event and must be
written to the append-only audit trail (CLAUDE.md, Security &
Multi-Tenancy) — a failed audit write degrades gracefully (logged, not
raised) rather than turning an already-failing auth check into a 500,
mirroring coordinator/app/audit_client.py's own contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import grpc
from fastapi import HTTPException, Request

from aecp_platform.errors import UnauthenticatedError
from app import auth, tenancy
from app.common.v1 import common_pb2
from app.observability.v1 import observability_pb2

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "aecp_session"
_SESSION_MAX_AGE_SECONDS = 3600


@dataclass
class RequestContext:
    session: auth.Session
    tenant_id: str


async def get_request_context(request: Request) -> RequestContext:
    """FastAPI dependency: verify the session cookie, derive the tenant
    id from it (never from client input), and enforce the per-tenant
    rate limit. Raises HTTPException(401) or HTTPException(429).
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        await _audit_auth_failure(request, reason="missing session cookie", actor_id="unknown")
        raise HTTPException(status_code=401, detail="Not authenticated")

    settings = request.app.state.settings
    try:
        session = auth.verify_session_cookie(
            cookie_value, settings.session_secret_key, max_age_seconds=_SESSION_MAX_AGE_SECONDS
        )
        tenant_id = tenancy.tenant_from_session(session)
    except UnauthenticatedError as exc:
        await _audit_auth_failure(request, reason=str(exc), actor_id="unknown")
        raise HTTPException(status_code=401, detail="Not authenticated") from exc

    rate_limiter = request.app.state.rate_limiter
    if not await rate_limiter.allow(f"{tenant_id}:{session.subject}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return RequestContext(session=session, tenant_id=tenant_id)


def get_clients(request: Request):
    """FastAPI dependency returning the shared InternalServiceClients
    built once at startup (app.state.clients) — see main.py.
    """
    return request.app.state.clients


async def _audit_auth_failure(request: Request, *, reason: str, actor_id: str) -> None:
    clients = getattr(request.app.state, "clients", None)
    if clients is None:
        return

    event = common_pb2.AuditEvent(
        event_id=str(uuid4()),
        tenant_id="",
        actor=common_pb2.Actor(kind=common_pb2.Actor.KIND_HUMAN, id=actor_id),
        action="auth_failure",
        resource=str(request.url.path),
        security_relevant=True,
    )
    event.occurred_at.FromDatetime(datetime.now(timezone.utc))

    try:
        await clients.observability().RecordAuditEvent(
            observability_pb2.RecordAuditEventRequest(event=event),
            metadata=clients.metadata(""),
        )
    except grpc.aio.AioRpcError as exc:
        logger.warning(
            "AuditService.RecordAuditEvent unavailable (%s); auth failure '%s' on "
            "'%s' was NOT durably recorded.",
            exc.code(),
            reason,
            request.url.path,
        )
