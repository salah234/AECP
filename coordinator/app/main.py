"""Coordinator service entrypoint.

Boots configuration, telemetry, the gRPC server (CoordinatorService), and
a small FastAPI app exposing only /healthz and /readyz for orchestrator
probes — all real traffic from the dashboard goes through the Gateway,
never directly to this service.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="aecp-coordinator")


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe: process is up."""
    raise NotImplementedError


@app.get("/readyz")
async def readyz() -> dict:
    """Readiness probe: dependent connections (Postgres, gRPC peers) are
    established.
    """
    raise NotImplementedError


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    raise NotImplementedError


def main() -> None:
    """Load Settings, init telemetry, and run the HTTP health server and
    gRPC server concurrently.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
