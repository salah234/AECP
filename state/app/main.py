"""State & Memory Layer service entrypoint."""

from __future__ import annotations

import asyncio

import asyncpg
import hypercorn.asyncio
from aecp_platform.dbtenant import TenantScopedPool
from fastapi import FastAPI
from hypercorn.config import Config

from app.config import Settings
from app.repository import StateRepository
from app.decision_log import DecisionLog
from app.ownership_map import OwnershipMap
from app.contracts import ContractRegistry
from app.drift import DriftDetector
from app.grpc_server import StateServicer, build_server


app = FastAPI(
    title="aecp-state",
)


repository: StateRepository | None = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
    }


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if repository is None:
        return {
            "status": "not_ready",
        }

    return {
        "status": "ready",
    }


async def serve_grpc() -> None:
    """
    Initialize dependencies and start gRPC.
    """

    global repository

    settings = Settings.from_env()
    print(settings.allowed_callers)

    from aecp_platform.storage import ObjectStorageClient

    pool = await asyncpg.create_pool(
        settings.postgres_dsn,
    )

    object_storage = ObjectStorageClient(
        bucket=settings.object_storage_bucket,
    )

    repository = StateRepository(
        pool=TenantScopedPool(pool),
        object_storage_client=object_storage,
    )

    decision_log = DecisionLog(
        repository,
    )

    ownership_map = OwnershipMap(
        repository,
    )

    contract_registry = ContractRegistry(
        repository,
    )

    drift_detector = DriftDetector(
        contract_registry,
        decision_log,
        repository,
    )

    servicer = StateServicer(
        decision_log=decision_log,
        ownership_map=ownership_map,
        contract_registry=contract_registry,
        drift_detector=drift_detector,
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

    print("AECP State gRPC server running")

    await server.wait_for_termination()


async def serve_http() -> None:
    """
    Start HTTP health server.
    """

    config = Config()

    settings = Settings.from_env()

    config.bind = [
        f"0.0.0.0:{settings.http_port}",
    ]

    await hypercorn.asyncio.serve(
        app,
        config,
    )


async def run() -> None:
    await asyncio.gather(
        serve_grpc(),
        serve_http(),
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
