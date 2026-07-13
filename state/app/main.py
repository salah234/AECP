"""State & Memory Layer service entrypoint."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
import hypercorn.asyncio
from hypercorn.config import Config

from app.config import Settings
from app.repository import StateRepository
from app.decision_log import DecisionLog
from app.ownership_map import OwnershipMap
from app.contracts import ContractRegistry
from app.drift import DriftDetector

from app.grpc_server import (
    StateServicer,
    build_server,
)


app = FastAPI(title="aecp-state")


repository: StateRepository | None = None


@app.get("/healthz")
async def healthz() -> dict:
    """
    Liveness probe.

    Kubernetes uses this to know the process is alive.
    """
    return {
        "status": "ok"
    }


@app.get("/readyz")
async def readyz() -> dict:
    """
    Readiness probe.

    Kubernetes uses this before sending traffic.
    """

    if repository is None:
        return {
            "status": "not_ready"
        }

    return {
        "status": "ready"
    }


async def serve_grpc() -> None:
    """
    Initialize dependencies and run gRPC server.
    """

    global repository

    settings = Settings.from_env()

    pool = await asyncpg.create_pool(
        settings.postgres_dsn
    )

    object_storage = ObjectStorageClient(
        bucket=settings.object_storage_bucket
    )

    repository = StateRepository(
        pool,
        object_storage,
    )


    # -------------------------
    # Application Services
    # -------------------------

    decision_log = DecisionLog(
        repository
    )

    ownership_map = OwnershipMap(
        repository
    )

    contract_registry = ContractRegistry(
        repository
    )

    drift_detector = DriftDetector(
        contract_registry,
        decision_log,
        repository,
    )


    # -------------------------
    # gRPC Layer
    # -------------------------

    servicer = StateServicer(
        decision_log=decision_log,
        ownership_map=ownership_map,
        contract_registry=contract_registry,
        drift_detector=drift_detector,
    )


    server = build_server(
        servicer=servicer,
        mtls_config=settings.mtls,
        allow_list=settings.allow_list,
    )


    await server.start()

    print(
        "AECP State gRPC server running on :50051"
    )


    await server.wait_for_termination()



async def serve_http() -> None:
    """
    Run FastAPI health server.
    """

    config = Config()

    config.bind = [
        "0.0.0.0:8080"
    ]

    await hypercorn.asyncio.serve(
        app,
        config,
    )



async def run() -> None:
    """
    Run HTTP and gRPC servers together.
    """

    await asyncio.gather(
        serve_grpc(),
        serve_http(),
    )



def main() -> None:
    """
    Service entrypoint.
    """

    asyncio.run(run())


if __name__ == "__main__":
    main()