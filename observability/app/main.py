"""Observability service entrypoint."""

from __future__ import annotations

import asyncio

import asyncpg
import uvicorn
from aecp_platform.dbtenant import TenantScopedPool
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.audit import AuditTrail
from app.config import Settings
from app.grpc_server import AuditServicer, build_server
from app.metrics import register_metrics
from app.repository import AuditRepository

app = FastAPI(title="aecp-observability")

_pool: asyncpg.Pool | None = None


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if _pool is None:
        return {"status": "not_ready"}

    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    register_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    global _pool

    settings = Settings.from_env()

    _pool = await asyncpg.create_pool(settings.postgres_dsn)
    repository = AuditRepository(TenantScopedPool(_pool))
    audit_trail = AuditTrail(repository)

    servicer = AuditServicer(audit_trail=audit_trail)

    server = build_server(
        servicer=servicer,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
        allow_list=settings.allowed_callers,
        port=settings.grpc_port,
    )

    await server.start()
    print("AECP Observability gRPC server running")
    await server.wait_for_termination()


async def serve_http() -> None:
    """Start the HTTP health/metrics server."""
    settings = Settings.from_env()

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.http_port,
        log_level="info",
    )
    await uvicorn.Server(config).serve()


async def run() -> None:
    await asyncio.gather(serve_grpc(), serve_http())


def main() -> None:
    """Load Settings, init telemetry, and run the HTTP health server and
    gRPC server concurrently.
    """
    register_metrics()
    asyncio.run(run())


if __name__ == "__main__":
    main()
