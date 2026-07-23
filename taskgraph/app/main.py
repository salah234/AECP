"""Task Graph service entrypoint."""

from __future__ import annotations

import asyncio
import json

import asyncpg
import uvicorn
from aecp_platform.dbtenant import TenantScopedPool
from aecp_platform.telemetry import init_tracing, shutdown_tracing
from fastapi import FastAPI

from app import ownership
from app.config import Settings
from app.graph import TaskGraph
from app.grpc_server import TaskGraphServicer, build_server
from app.repository import TaskNodeRepository

app = FastAPI(title="aecp-taskgraph")

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Make JSONB columns round-trip as plain dicts.

    Without this, asyncpg neither serializes Python objects to JSON on
    write nor parses JSONB text back to a dict on read, so
    TaskNode.definition_of_done (a nested pydantic model) fails on both
    sides of the wire.
    """
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if _pool is None:
        return {"status": "not_ready"}

    return {"status": "ready"}


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    global _pool

    settings = Settings.from_env()

    _pool = await asyncpg.create_pool(settings.postgres_dsn, init=_init_connection)
    repository = TaskNodeRepository(TenantScopedPool(_pool))
    graph = TaskGraph(repository)

    servicer = TaskGraphServicer(
        graph=graph,
        ownership_module=ownership,
        repository=repository,
    )

    server = build_server(
        servicer=servicer,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
        allow_list=settings.allowed_callers,
        port=settings.grpc_port,
    )

    await server.start()
    print("AECP TaskGraph gRPC server running")
    await server.wait_for_termination()


async def serve_http() -> None:
    """Start the HTTP health server."""
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
    settings = Settings.from_env()
    init_tracing(service_name="taskgraph", collector_endpoint=settings.otel_collector_endpoint)
    try:
        asyncio.run(run())
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
