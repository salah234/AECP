"""Gateway service entrypoint.

The only AECP HTTP surface exposed outside the private network. All other
services bind gRPC only and are unreachable except via mTLS from inside
the mesh (see deploy/k8s/networkpolicy). Gateway itself binds no inbound
gRPC server (gateway-edges.yaml's ingress rule only opens the HTTP port
to ingress-nginx), so there's no equivalent of coordinator's
asyncio.gather(serve_grpc(), serve_http()) here — just one HTTP server,
wired up via FastAPI's lifespan so the outbound gRPC channels to internal
services are built inside a running event loop (grpc.aio's own
requirement), not at import time.
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from aecp_platform.errors import PermissionDeniedError, UnauthenticatedError
from aecp_platform.telemetry import init_tracing, shutdown_tracing
from app import auth
from app.config import Settings
from app.deps import SESSION_COOKIE_NAME, RequestContext, get_request_context
from app.proxy import InternalServiceClients
from app.rate_limit import RateLimiter
from app.routers import agents, coordinator, decisions, escalations, tasks

_tracer = trace.get_tracer("aecp.gateway")

logger = logging.getLogger(__name__)

_OIDC_STATE_COOKIE_NAME = "aecp_oidc_state"
_OIDC_STATE_COOKIE_MAX_AGE_SECONDS = 300
_SESSION_MAX_AGE_SECONDS = 3600

_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ready

    settings = Settings.from_env()
    init_tracing(service_name="gateway", collector_endpoint=settings.otel_collector_endpoint)
    app.state.settings = settings
    app.state.oidc_client = auth.OIDCClient(
        settings.oidc_issuer_url,
        settings.oidc_client_id,
        settings.oidc_client_secret_key,
        settings.oidc_redirect_url,
    )
    app.state.clients = InternalServiceClients(settings)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_requests_per_minute)

    _ready = True
    yield
    _ready = False
    shutdown_tracing()


app = FastAPI(title="aecp-gateway", lifespan=lifespan)
# The dashboard (localhost:3000) is a different origin than gateway
# (localhost:8080) even in local dev, so the browser blocks every fetch
# from it (surfacing as "Failed to fetch", not a readable HTTP error)
# unless gateway explicitly allows it. allow_credentials=True is required
# for the session cookie to be sent/received cross-origin, which in turn
# requires an explicit origin here — "*" is rejected by browsers when
# credentials are allowed. Read directly from the environment (not
# Settings.from_env(), which only runs inside lifespan, after the app
# object — and this middleware — must already exist).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("DASHBOARD_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    """Open a SERVER span per inbound request, so the trace_id gateway
    hands back from an action like POST /api/v1/coordinator/schedule
    (see routers/coordinator.py's use of
    aecp_platform.telemetry.current_trace_id_hex) actually roots the
    whole downstream call chain, rather than starting mid-trace at
    whichever internal service happens to run TracingServerInterceptor
    first. Manual rather than opentelemetry-instrumentation-fastapi: this
    codebase prefers a small amount of explicit code here over a new
    dependency for what is otherwise a two-line span.
    """
    with _tracer.start_as_current_span(
        f"{request.method} {request.url.path}", kind=SpanKind.SERVER
    ):
        return await call_next(request)


app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(coordinator.router)
app.include_router(decisions.router)
app.include_router(escalations.router)


@app.exception_handler(UnauthenticatedError)
async def handle_unauthenticated(request: Request, exc: UnauthenticatedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(PermissionDeniedError)
async def handle_permission_denied(request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe: process is up."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    """Readiness probe: internal service clients are constructed."""
    return {"status": "ready" if _ready else "not_ready"}


_DEV_OIDC_SECRET_PLACEHOLDER = "changeme"


@app.get("/auth/dev-login")
async def dev_login(
    request: Request,
    subject: str = "em-1",
    tenant_id: str = "11111111-1111-1111-1111-111111111111",
    role: str = "em",
) -> RedirectResponse:
    """DEV-ONLY session bypass, skipping the OIDC round-trip entirely.

    Gated on OIDC_CLIENT_SECRET still being the literal placeholder value
    from .env.example — the same signal that already means "no real IdP
    is configured" everywhere else in this codebase. The moment a real
    secret is set, this route 404s, so it cannot leak into any deployment
    that has actually configured OIDC. This is a trust-boundary change
    (CLAUDE.md Tier 3) scoped as tightly as possible; see
    security/THREAT_MODEL.md for the corresponding entry.
    """
    settings = request.app.state.settings
    if settings.oidc_client_secret_key != _DEV_OIDC_SECRET_PLACEHOLDER:
        raise HTTPException(status_code=404)

    logger.warning(
        "DEV LOGIN BYPASS used: subject=%s tenant_id=%s role=%s — "
        "never enabled outside local dev (see /auth/dev-login docstring)",
        subject,
        tenant_id,
        role,
    )

    session = auth.Session(
        subject=subject,
        tenant_id=tenant_id,
        role=role,
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=_SESSION_MAX_AGE_SECONDS)).isoformat(),
    )
    cookie_value = auth.issue_session_cookie(session, settings.session_secret_key)

    response = RedirectResponse(settings.dashboard_origin)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect to the OIDC provider's authorization endpoint.

    In dev (no real OIDC secret configured — see /auth/dev-login), hand
    off to the bypass instead of building a real authorization URL that
    would only 401 at the IdP. This is the single entry point
    AuthGuard.tsx already calls on every unauthenticated page load, so
    gating here — rather than in the dashboard — means the dashboard
    needs no dev-vs-real-IdP branching of its own.
    """
    settings = request.app.state.settings
    if settings.oidc_client_secret_key == _DEV_OIDC_SECRET_PLACEHOLDER:
        return RedirectResponse(str(request.url_for("dev_login")))

    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(request.app.state.oidc_client.authorization_redirect_url(state))
    redirect.set_cookie(
        _OIDC_STATE_COOKIE_NAME,
        state,
        max_age=_OIDC_STATE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return redirect


@app.get("/auth/callback")
async def auth_callback(code: str, state: str, request: Request) -> RedirectResponse:
    """Exchange the authorization code and issue a session cookie."""
    expected_state = request.cookies.get(_OIDC_STATE_COOKIE_NAME)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=401, detail="Invalid or missing OIDC state")

    try:
        session = await request.app.state.oidc_client.exchange_code(code, state)
    except UnauthenticatedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    cookie_value = auth.issue_session_cookie(session, request.app.state.settings.session_secret_key)

    # Gateway serves no browsable "/" of its own — the dashboard is the
    # only human-facing page, and it lives at a different origin.
    response = RedirectResponse(request.app.state.settings.dashboard_origin)
    response.delete_cookie(_OIDC_STATE_COOKIE_NAME)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@app.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged_out"}


@app.get("/api/v1/me")
async def me(ctx: RequestContext = Depends(get_request_context)) -> dict:
    """The dashboard's lib/auth.ts expects this to resolve the current
    user without ever verifying the OIDC token itself.
    """
    return {"subject": ctx.session.subject, "tenantId": ctx.tenant_id, "role": ctx.session.role}


def main() -> None:
    """Load Settings and run the HTTP server."""
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port)


if __name__ == "__main__":
    main()
