"""Agent Pool service entrypoint."""

from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI

from app.channels import build_client_channel
from app.config import Settings
from app.coordinator_client import CoordinatorClient
from app.grpc_server import AgentPoolServicer, build_server
from app.handoff import HandoffCoordinator
from app.hydration import ContextHydrator
from app.identity import CredentialIssuer, generate_signing_key
from app.lifecycle import LifecycleManager
from app.pool import AgentPool
from app.sandbox import Sandbox
from app.state_client import StateClient

app = FastAPI(title="aecp-agents")

_lifecycle_manager: LifecycleManager | None = None

# Sessions are disposable and in-memory (see lifecycle.py); a process
# restart already invalidates every issued credential along with the
# registry that tracks them, so an ephemeral, randomly-generated signing
# key at startup is consistent with that design rather than a gap in it.
# A durable signing key belongs in aecp_platform.secrets once that module
# is implemented (Tier 3, owned by /platform) — see identity.py.
_SIGNING_KEY = generate_signing_key()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if _lifecycle_manager is None:
        return {"status": "not_ready"}

    return {"status": "ready"}


async def _reap_loop(
    lifecycle_manager: LifecycleManager,
    pool: AgentPool,
    coordinator_client: CoordinatorClient,
    interval_seconds: float,
) -> None:
    """Periodically terminate TTL-expired sessions and notify the
    Coordinator so it can reschedule their tasks (see
    lifecycle.reap_expired's docstring and coordinator_client.py for why
    ReportBlocker is the RPC used for that notification).
    """
    while True:
        await asyncio.sleep(interval_seconds)

        expired = await lifecycle_manager.reap_expired()
        for session in expired:
            await pool.release_slot(session.tenant_id)
            await coordinator_client.report_blocker(
                task_id=session.task_id,
                agent_id=session.session_id,
                description=(
                    f"Agent session {session.session_id} exceeded its TTL "
                    "and was reaped; task needs rescheduling."
                ),
            )


async def serve_grpc() -> None:
    """Build and run the gRPC server (see grpc_server.build_server) until
    shutdown is signaled.
    """
    global _lifecycle_manager

    settings = Settings.from_env()

    sandbox = Sandbox(image=settings.sandbox_image)
    identity_issuer = CredentialIssuer(signing_key=_SIGNING_KEY)
    lifecycle_manager = LifecycleManager(
        sandbox=sandbox,
        identity_issuer=identity_issuer,
        session_ttl_seconds=settings.session_ttl_seconds,
    )
    _lifecycle_manager = lifecycle_manager

    state_channel = build_client_channel(
        settings.state_addr,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
    )
    state_client = StateClient(state_channel, caller_id="agents")

    coordinator_channel = build_client_channel(
        settings.coordinator_addr,
        mtls_cert_file=settings.mtls_cert_file,
        mtls_key_file=settings.mtls_key_file,
        mtls_ca_file=settings.mtls_ca_file,
    )
    coordinator_client = CoordinatorClient(coordinator_channel, caller_id="agents")

    hydrator = ContextHydrator(lifecycle_manager=lifecycle_manager, state_client=state_client)
    handoff_coordinator = HandoffCoordinator(
        lifecycle_manager=lifecycle_manager,
        hydrator=hydrator,
        state_client=state_client,
    )
    pool = AgentPool(lifecycle_manager=lifecycle_manager)

    servicer = AgentPoolServicer(
        lifecycle_manager=lifecycle_manager,
        hydrator=hydrator,
        handoff_coordinator=handoff_coordinator,
        pool=pool,
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
    print("AECP Agent Pool gRPC server running")

    reap_interval = max(1.0, min(settings.session_ttl_seconds / 2, 30.0))
    reap_task = asyncio.create_task(
        _reap_loop(lifecycle_manager, pool, coordinator_client, reap_interval)
    )

    try:
        await server.wait_for_termination()
    finally:
        reap_task.cancel()


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
    asyncio.run(run())


if __name__ == "__main__":
    main()
