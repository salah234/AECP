"""Gateway service entrypoint.

The only AECP HTTP surface exposed outside the private network. All other
services bind gRPC only and are unreachable except via mTLS from inside
the mesh (see deploy/k8s/networkpolicy).
"""

from __future__ import annotations

from fastapi import FastAPI

from .routers import agents, decisions, escalations, tasks

app = FastAPI(title="aecp-gateway")
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(decisions.router)
app.include_router(escalations.router)


@app.get("/healthz")
async def healthz() -> dict:
    raise NotImplementedError


@app.get("/readyz")
async def readyz() -> dict:
    raise NotImplementedError


@app.get("/auth/login")
async def login():
    """Redirect to the OIDC provider's authorization endpoint."""
    raise NotImplementedError


@app.get("/auth/callback")
async def auth_callback(code: str, state: str):
    """Exchange the authorization code and issue a session cookie."""
    raise NotImplementedError


@app.post("/auth/logout")
async def logout():
    raise NotImplementedError


def main() -> None:
    """Load Settings, init telemetry, and run the HTTP server."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
