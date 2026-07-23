"""Coordinator service entrypoint.

Boots configuration, the gRPC server (CoordinatorService), and a small
FastAPI app exposing only /healthz and /readyz for orchestrator probes —
all real traffic from the dashboard goes through the Gateway, never
directly to this service.
"""

from __future__ import annotations

import asyncio

import grpc
import uvicorn
from aecp_platform.identity import AllowList, MTLSConfig, ServiceID
from aecp_platform.telemetry import init_tracing, shutdown_tracing
from fastapi import FastAPI

from app.agent_pool_client import AgentPoolClient
from app.assignment import AssignmentEngine
from app.audit_client import AuditClient
from app.channels import build_client_channel
from app.config import Settings
from app.grpc_server import CoordinatorServicer, build_server
from app.integration_client import IntegrationClient
from app.scheduler import Scheduler
from app.state_client import StateClient
from app.taskgraph_client import TaskGraphClient
from app.tradeoff import TradeoffResolver

app = FastAPI(title="aecp-coordinator")

_ready = False


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe: process is up."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    """Readiness probe: dependent connections (Postgres, gRPC peers) are
    established.
    """
    return {"status": "ready" if _ready else "not_ready"}


def _build_channel(settings: Settings, target: str) -> grpc.aio.Channel:
    return build_client_channel(
        target,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
    )


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    global _ready

    settings = Settings.from_env()

    taskgraph_client = TaskGraphClient(
        _build_channel(settings, settings.taskgraph_addr), caller_id="coordinator"
    )
    state_client = StateClient(
        _build_channel(settings, settings.state_addr), caller_id="coordinator"
    )
    agent_pool_client = AgentPoolClient(
        _build_channel(settings, settings.agents_addr), caller_id="coordinator"
    )
    integration_client = IntegrationClient(
        _build_channel(settings, settings.integration_addr), caller_id="coordinator"
    )
    audit_client = AuditClient(
        _build_channel(settings, settings.observability_addr), caller_id="coordinator"
    )

    scheduler = Scheduler(taskgraph_client, integration_client)
    assignment_engine = AssignmentEngine(agent_pool_client, state_client, taskgraph_client)
    tradeoff_resolver = TradeoffResolver(state_client, audit_client, taskgraph_client)

    servicer = CoordinatorServicer(
        scheduler=scheduler,
        assignment_engine=assignment_engine,
        tradeoff_resolver=tradeoff_resolver,
        agent_pool_client=agent_pool_client,
    )

    mtls_config = None
    if settings.mtls_cert_file and settings.mtls_key_file and settings.mtls_ca_file:
        mtls_config = MTLSConfig(
            self_id=ServiceID("spiffe://aecp/dev/coordinator"),
            cert_file=settings.mtls_cert_file,
            key_file=settings.mtls_key_file,
            ca_file=settings.mtls_ca_file,
        )

    allow_list = AllowList(*settings.allowed_callers)

    server = build_server(servicer, mtls_config, allow_list, port=settings.grpc_port)

    await server.start()
    print("AECP Coordinator gRPC server running")
    _ready = True

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
    init_tracing(service_name="coordinator", collector_endpoint=settings.otel_collector_endpoint)
    try:
        asyncio.run(run())
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
