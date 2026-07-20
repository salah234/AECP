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
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from aecp_platform.errors import PermissionDeniedError, UnauthenticatedError
from app import auth
from app.config import Settings
from app.deps import SESSION_COOKIE_NAME, RequestContext, get_request_context
from app.proxy import InternalServiceClients
from app.rate_limit import RateLimiter
from app.routers import agents, decisions, escalations, tasks

logger = logging.getLogger(__name__)

_OIDC_STATE_COOKIE_NAME = "aecp_oidc_state"
_OIDC_STATE_COOKIE_MAX_AGE_SECONDS = 300
_SESSION_MAX_AGE_SECONDS = 3600

_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ready

    settings = Settings.from_env()
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


app = FastAPI(title="aecp-gateway", lifespan=lifespan)
app.include_router(tasks.router)
app.include_router(agents.router)
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


@app.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect to the OIDC provider's authorization endpoint."""
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

    response = RedirectResponse("/")
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
