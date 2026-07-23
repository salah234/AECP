"""Integration service entrypoint."""

from __future__ import annotations

import asyncio

import uvicorn
from aecp_platform.telemetry import init_tracing, shutdown_tracing
from fastapi import FastAPI

from app.channels import build_client_channel
from app.config import Settings
from app.conflict import ConflictDetector
from app.grpc_server import IntegrationServicer, build_server
from app.merge_policy import MergePolicyResolver
from app.semantic_diff import SemanticDiffer
from app.state_client import StateClient
from app.taskgraph_client import TaskGraphClient

app = FastAPI(title="aecp-integration")

_ready = False


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if not _ready:
        return {"status": "not_ready"}

    return {"status": "ready"}


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    global _ready

    settings = Settings.from_env()

    taskgraph_channel = build_client_channel(
        settings.taskgraph_addr,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
    )
    state_channel = build_client_channel(
        settings.state_addr,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
    )

    taskgraph_client = TaskGraphClient(taskgraph_channel)
    state_client = StateClient(state_channel)

    semantic_differ = SemanticDiffer(state_client, taskgraph_client)
    conflict_detector = ConflictDetector(taskgraph_client, semantic_differ)
    merge_policy_resolver = MergePolicyResolver()

    servicer = IntegrationServicer(
        conflict_detector=conflict_detector,
        merge_policy_resolver=merge_policy_resolver,
        semantic_differ=semantic_differ,
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
    _ready = True
    print("AECP Integration gRPC server running")
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
    init_tracing(service_name="integration", collector_endpoint=settings.otel_collector_endpoint)
    try:
        asyncio.run(run())
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
