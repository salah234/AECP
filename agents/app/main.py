"""Agent Pool service entrypoint."""

from __future__ import annotations

import asyncio

import uvicorn
from aecp_platform.telemetry import init_tracing, shutdown_tracing
from fastapi import FastAPI

from app.channels import build_client_channel
from app.config import Settings
from app.coordinator_client import CoordinatorClient
from app.execution_backends.base import ExecutionBackend
from app.execution_backends.claude_cli import ClaudeCliBackend
from app.execution_backends.cohere_backend import CohereBackend
from app.executor import AgentExecutor
from app.grpc_server import AgentPoolServicer, build_server
from app.handoff import HandoffCoordinator
from app.hydration import ContextHydrator
from app.identity import CredentialIssuer, generate_signing_key
from app.lifecycle import LifecycleManager
from app.pool import AgentPool
from app.sandbox import Sandbox
from app.state_client import StateClient
from app.target_repo import TargetRepoCheckout

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
                tenant_id=session.tenant_id,
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

    target_repo = TargetRepoCheckout(
        repo_path=settings.target_repo_path,
        repo_url=settings.target_repo_url,
    )
    backend: ExecutionBackend
    if settings.agent_execution_backend == "cohere":
        backend = CohereBackend(
            cohere_api_key=settings.cohere_api_key,
            cohere_model=settings.cohere_model,
            max_iterations=settings.cohere_max_tool_iterations,
        )
    else:
        backend = ClaudeCliBackend(
            claude_binary=settings.claude_binary,
            anthropic_api_key=settings.anthropic_api_key,
            agent_model=settings.agent_model,
            permission_mode=settings.agent_permission_mode,
            allowed_tools=settings.agent_allowed_tools,
        )
    executor = AgentExecutor(
        hydrator=hydrator,
        coordinator_client=coordinator_client,
        target_repo=target_repo,
        backend=backend,
        execution_timeout_seconds=settings.agent_execution_timeout_seconds,
        lifecycle_manager=lifecycle_manager,
    )
    # Wired post-construction, not via LifecycleManager's constructor:
    # AgentExecutor needs `hydrator`, which needs `lifecycle_manager` — a
    # straight constructor dependency in the other direction would be
    # circular. See lifecycle.py's execution_canceller docstring.
    lifecycle_manager.execution_canceller = executor.cancel

    handoff_coordinator = HandoffCoordinator(
        lifecycle_manager=lifecycle_manager,
        hydrator=hydrator,
        state_client=state_client,
        executor=executor,
    )
    pool = AgentPool(lifecycle_manager=lifecycle_manager)

    servicer = AgentPoolServicer(
        lifecycle_manager=lifecycle_manager,
        hydrator=hydrator,
        handoff_coordinator=handoff_coordinator,
        pool=pool,
        executor=executor,
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
        # Awaited (unlike reap_task.cancel() above, which doesn't wait
        # for confirmation): an orphaned live claude subprocess matters
        # more than an orphaned in-memory loop. See executor.shutdown's
        # docstring.
        await executor.shutdown()


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
    init_tracing(service_name="agents", collector_endpoint=settings.otel_collector_endpoint)
    try:
        asyncio.run(run())
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
