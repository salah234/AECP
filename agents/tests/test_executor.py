"""Tests for AgentExecutor's own orchestration (hydrate -> checkout ->
backend.run -> report_completion/report_blocker branching, cancellation)
independent of any concrete ExecutionBackend — see
tests/execution_backends/ for backend-specific behavior.
"""

from __future__ import annotations

import asyncio

from app.common.v1 import common_pb2
from app.execution_backends.base import ExecutionOutcome
from app.executor import AgentExecutor
from app.hydration import ContextBundle
from app.lifecycle import AgentSession, LifecycleManager
from app.taskgraph.v1 import taskgraph_pb2

from .fakes import (
    FakeCoordinatorClient,
    FakeExecutionBackend,
    FakeIdentityIssuer,
    FakeSandbox,
    FakeTargetRepoCheckout,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"
SESSION_ID = "33333333-3333-3333-3333-333333333333"


def make_session() -> AgentSession:
    return AgentSession(
        session_id=SESSION_ID,
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        status="ACTIVE",
        granted_risk_tier="RISK_TIER_LOCAL",
    )


def make_bundle() -> ContextBundle:
    node = taskgraph_pb2.TaskNode(
        task_id=TASK_ID,
        tenant_id=TENANT_ID,
        title="Add retry to webhook sender",
        description="Retries should use exponential backoff.",
        risk_tier=common_pb2.RISK_TIER_LOCAL,
    )
    ownership = common_pb2.OwnershipBoundary(path_globs=["services/webhooks/**"])
    return ContextBundle(
        task_id=TASK_ID,
        task_node=node.SerializeToString(),
        ownership_boundary=ownership.SerializeToString(),
        relevant_interface_contracts=[],
        relevant_decision_log_entries=[],
    )


class FakeHydrator:
    def __init__(self, bundle: ContextBundle) -> None:
        self.bundle = bundle

    async def hydrate(self, session_id: str) -> ContextBundle:
        return self.bundle


def make_executor(
    *,
    backend=None,
    target_repo=None,
    coordinator_client=None,
    execution_timeout_seconds: float = 5.0,
    lifecycle_manager=None,
):
    coordinator_client = coordinator_client or FakeCoordinatorClient()
    target_repo = target_repo or FakeTargetRepoCheckout()
    backend = backend or FakeExecutionBackend()
    hydrator = FakeHydrator(make_bundle())
    executor = AgentExecutor(
        hydrator=hydrator,
        coordinator_client=coordinator_client,
        target_repo=target_repo,
        backend=backend,
        execution_timeout_seconds=execution_timeout_seconds,
        lifecycle_manager=lifecycle_manager,
    )
    return executor, coordinator_client, target_repo, backend


async def test_happy_path_reports_completion() -> None:
    backend = FakeExecutionBackend(
        outcome=ExecutionOutcome(
            success=True,
            summary="Added exponential backoff to webhook retries.",
            rationale="Added exponential backoff to webhook retries.",
        )
    )
    executor, coordinator_client, target_repo, backend = make_executor(backend=backend)
    session = make_session()

    await executor._run(session, "/fake/scratch/33333333")

    assert coordinator_client.reported_completions == [
        {
            "task_id": TASK_ID,
            "tenant_id": TENANT_ID,
            "agent_id": SESSION_ID,
            "summary": "Added exponential backoff to webhook retries.",
            "rationale": "Added exponential backoff to webhook retries.",
        }
    ]
    assert coordinator_client.reported_blockers == []
    assert len(backend.calls) == 1
    assert target_repo.calls == [("/fake/scratch/33333333", SESSION_ID)]


async def test_failed_outcome_reports_blocker() -> None:
    backend = FakeExecutionBackend(
        outcome=ExecutionOutcome(success=False, summary="", rationale="backend-specific failure")
    )
    executor, coordinator_client, _target_repo, _backend = make_executor(backend=backend)

    await executor._run(make_session(), "/fake/scratch/33333333")

    assert len(coordinator_client.reported_blockers) == 1
    assert "backend-specific failure" in coordinator_client.reported_blockers[0]["description"]
    assert coordinator_client.reported_completions == []


async def test_checkout_failure_reports_blocker_without_running_backend() -> None:
    target_repo = FakeTargetRepoCheckout(fail=True)
    executor, coordinator_client, _target_repo, backend = make_executor(target_repo=target_repo)

    await executor._run(make_session(), "/fake/scratch/33333333")

    assert len(coordinator_client.reported_blockers) == 1
    assert backend.calls == []


async def test_backend_exception_reports_blocker() -> None:
    class _RaisingBackend:
        async def run(self, *, prompt, repo_dir, timeout_seconds):
            raise OSError("backend blew up")

    executor, coordinator_client, _target_repo, _backend = make_executor(backend=_RaisingBackend())

    await executor._run(make_session(), "/fake/scratch/33333333")

    assert len(coordinator_client.reported_blockers) == 1
    assert "backend blew up" in coordinator_client.reported_blockers[0]["description"]


async def test_cancel_interrupts_in_flight_run_without_reporting() -> None:
    hang_event = asyncio.Event()
    backend = FakeExecutionBackend(hang_event=hang_event)
    executor, coordinator_client, _target_repo, _backend = make_executor(backend=backend)
    session = make_session()

    executor.spawn_background(session, "/fake/scratch/33333333")
    await asyncio.sleep(0)  # let _run start and reach the (never-set) hang_event.wait()

    await executor.cancel(session.session_id)

    assert coordinator_client.reported_completions == []
    assert coordinator_client.reported_blockers == []
    assert session.session_id not in executor._tasks


async def test_shutdown_cancels_all_tracked_tasks() -> None:
    hang_event = asyncio.Event()
    backend = FakeExecutionBackend(hang_event=hang_event)
    executor, coordinator_client, _target_repo, _backend = make_executor(backend=backend)
    session = make_session()

    executor.spawn_background(session, "/fake/scratch/33333333")
    await asyncio.sleep(0)

    await executor.shutdown()

    assert coordinator_client.reported_completions == []
    assert coordinator_client.reported_blockers == []


async def test_run_terminates_its_own_session_after_completing() -> None:
    """Regression test: without this, a session stays ACTIVE in
    LifecycleManager forever after its execution finishes (success or
    blocker) — only the TTL reap loop would eventually catch it, up to
    SESSION_TTL_SECONDS later.
    """
    manager = LifecycleManager(
        sandbox=FakeSandbox(), identity_issuer=FakeIdentityIssuer(), session_ttl_seconds=3600
    )
    session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )
    backend = FakeExecutionBackend(
        outcome=ExecutionOutcome(success=True, summary="ok", rationale="ok")
    )
    executor, _coordinator_client, _target_repo, _backend = make_executor(
        backend=backend, coordinator_client=FakeCoordinatorClient(), lifecycle_manager=manager
    )

    handle = await manager.get_sandbox_handle(session.session_id)
    executor.spawn_background(session, handle.scratch_dir)

    for _ in range(5):
        await asyncio.sleep(0)

    assert await manager.get(session.session_id) is None


async def test_run_terminates_its_own_session_after_blocker() -> None:
    manager = LifecycleManager(
        sandbox=FakeSandbox(), identity_issuer=FakeIdentityIssuer(), session_ttl_seconds=3600
    )
    session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )
    backend = FakeExecutionBackend(
        outcome=ExecutionOutcome(success=False, summary="", rationale="something went wrong")
    )
    executor, _coordinator_client, _target_repo, _backend = make_executor(
        backend=backend, lifecycle_manager=manager
    )

    handle = await manager.get_sandbox_handle(session.session_id)
    executor.spawn_background(session, handle.scratch_dir)

    for _ in range(5):
        await asyncio.sleep(0)

    assert await manager.get(session.session_id) is None
