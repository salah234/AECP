"""Real end-to-end integration test: boots postgres + all 7 backend
services (see docker-compose.test.yml in this directory) as real Docker
containers and drives one full task lifecycle over real gRPC — no fakes,
no mocks. This file's own tests only exercise taskgraph/state/agents/
coordinator directly; see test_full_system_e2e.py in this same directory
for the integration/observability/gateway coverage now that the topology
includes them too. This is deliberately separate from coordinator/tests/'s
fast, hermetic unit suite: it requires Docker and is opt-in via the
AECP_RUN_DOCKER_INTEGRATION_TESTS env var so `pytest`/`make test` stays
fast by default and never silently fails on a machine without Docker.

Run it explicitly:

    docker compose -f coordinator/tests/integration/docker-compose.test.yml \
        up -d --build
    # apply migrations once (see apply_migrations() below for the exact
    # commands, or run them by hand against the exposed postgres port)
    AECP_RUN_DOCKER_INTEGRATION_TESTS=1 pytest coordinator/tests/integration -q
    docker compose -f coordinator/tests/integration/docker-compose.test.yml \
        down -v
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import grpc
import pytest

from app.agents.v1 import agents_pb2, agents_pb2_grpc
from app.common.v1 import common_pb2
from app.coordinator.v1 import coordinator_pb2, coordinator_pb2_grpc
from app.taskgraph.v1 import taskgraph_pb2, taskgraph_pb2_grpc

pytestmark = pytest.mark.skipif(
    os.getenv("AECP_RUN_DOCKER_INTEGRATION_TESTS") != "1",
    reason="opt-in: set AECP_RUN_DOCKER_INTEGRATION_TESTS=1 and boot "
    "docker-compose.test.yml first (see this file's module docstring)",
)

TASKGRAPH_ADDR = "localhost:55052"
STATE_ADDR = "localhost:55051"
AGENTS_ADDR = "localhost:55053"
COORDINATOR_ADDR = "localhost:55054"
POSTGRES_DSN = "postgresql://aecp:aecp_dev_only@localhost:55432/aecp"

REPO_ROOT = Path(__file__).resolve().parents[3]


def _caller_metadata(caller_id: str) -> tuple[tuple[str, str], ...]:
    return (("caller-id", caller_id),)


async def _wait_for_channel_ready(target: str, timeout_seconds: float = 60.0) -> None:
    channel = grpc.aio.insecure_channel(target)
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    try:
        while time.monotonic() < deadline:
            try:
                await asyncio.wait_for(channel.channel_ready(), timeout=2.0)
                return
            except Exception as exc:  # noqa: BLE001 - retry loop
                last_error = exc
                await asyncio.sleep(1.0)
    finally:
        await channel.close()
    raise TimeoutError(f"{target} never became ready: {last_error}")


@pytest.fixture(scope="module", autouse=True)
def _wait_for_stack_ready():
    async def wait_all():
        await asyncio.gather(
            _wait_for_channel_ready(TASKGRAPH_ADDR),
            _wait_for_channel_ready(STATE_ADDR),
            _wait_for_channel_ready(AGENTS_ADDR),
            _wait_for_channel_ready(COORDINATOR_ADDR),
        )

    asyncio.run(wait_all())


@pytest.fixture(scope="module")
def tenant_id() -> str:
    return str(uuid4())


@pytest.mark.asyncio
async def test_full_task_lifecycle_across_real_services(tenant_id: str) -> None:
    # 1. Create a ready task node directly against the real TaskGraph
    #    container.
    async with grpc.aio.insecure_channel(TASKGRAPH_ADDR) as channel:
        taskgraph_stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        create_response = await taskgraph_stub.CreateTaskNode(
            taskgraph_pb2.CreateTaskNodeRequest(
                node=taskgraph_pb2.TaskNode(
                    tenant_id=tenant_id,
                    title="Add retry to flaky webhook call",
                    description="Integration test task",
                    risk_tier=common_pb2.RISK_TIER_LOCAL,
                    status=common_pb2.TASK_STATUS_PENDING,
                    ownership=common_pb2.OwnershipBoundary(
                        path_globs=["gateway/app/webhooks.py"]
                    ),
                )
            ),
            metadata=_caller_metadata("coordinator"),
        )
        task_id = create_response.node.task_id
        assert task_id

    # 2. Ask the real Coordinator to schedule this tenant's ready work.
    #    This exercises Scheduler -> TaskGraphClient, AssignmentEngine ->
    #    TaskGraphClient + AgentPoolClient + StateClient, all over real
    #    gRPC to real containers.
    async with grpc.aio.insecure_channel(COORDINATOR_ADDR) as channel:
        coordinator_stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        schedule_response = await coordinator_stub.Schedule(
            coordinator_pb2.ScheduleRequest(tenant_id=tenant_id),
            metadata=_caller_metadata("test-client"),
        )

    assert len(schedule_response.decisions) == 1, (
        "expected exactly one assignment decision for the single ready task"
    )
    decision = schedule_response.decisions[0]
    assert decision.task_id == task_id
    assert decision.granted_risk_tier == common_pb2.RISK_TIER_LOCAL
    agent_session_id = decision.agent_id
    assert agent_session_id, "AssignmentEngine did not receive a real session id from Agent Pool"

    # 3. Confirm the real Agent Pool container actually holds that
    #    session (proves SpawnSession really executed there, not just
    #    that Coordinator *thinks* it did).
    async with grpc.aio.insecure_channel(AGENTS_ADDR) as channel:
        agents_stub = agents_pb2_grpc.AgentPoolServiceStub(channel)
        hydrate_response = await agents_stub.HydrateContext(
            agents_pb2.HydrateContextRequest(session_id=agent_session_id),
            metadata=_caller_metadata("coordinator"),
        )
        assert hydrate_response.context_bundle

    # 4. Confirm the real TaskGraph container now reflects ASSIGNED —
    #    proves AssignmentEngine's UpdateTaskStatus call landed for real.
    async with grpc.aio.insecure_channel(TASKGRAPH_ADDR) as channel:
        taskgraph_stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        get_response = await taskgraph_stub.GetTaskNode(
            taskgraph_pb2.GetTaskNodeRequest(task_id=task_id, tenant_id=tenant_id),
            metadata=_caller_metadata("coordinator"),
        )
        assert get_response.node.status == common_pb2.TASK_STATUS_ASSIGNED

    # 5. Escalate to an Architectural tier: must route to a human, never
    #    auto-approved by Coordinator alone (Escalation Policy). This
    #    round-trips through the real TaskGraph (tenant_id lookup) and
    #    would-be Observability audit call (which gracefully degrades
    #    since no observability container exists in this topology).
    async with grpc.aio.insecure_channel(COORDINATOR_ADDR) as channel:
        coordinator_stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        escalate_response = await coordinator_stub.Escalate(
            coordinator_pb2.EscalateRequest(
                task_id=task_id,
                tenant_id=tenant_id,
                agent_id=agent_session_id,
                reason="turned out to touch a shared auth boundary",
                requested_risk_tier=common_pb2.RISK_TIER_ARCHITECTURAL,
            ),
            metadata=_caller_metadata("test-client"),
        )
    assert escalate_response.approved is False
    assert escalate_response.decided_by == "human"

    # 6. Report a blocker; confirm it lands as BLOCKED on the real
    #    TaskGraph container.
    async with grpc.aio.insecure_channel(COORDINATOR_ADDR) as channel:
        coordinator_stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        blocker_response = await coordinator_stub.ReportBlocker(
            coordinator_pb2.ReportBlockerRequest(
                task_id=task_id,
                tenant_id=tenant_id,
                agent_id=agent_session_id,
                description="upstream webhook sandbox is unreachable",
            ),
            metadata=_caller_metadata("test-client"),
        )
    assert blocker_response.acknowledged is True

    async with grpc.aio.insecure_channel(TASKGRAPH_ADDR) as channel:
        taskgraph_stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        final_response = await taskgraph_stub.GetTaskNode(
            taskgraph_pb2.GetTaskNodeRequest(task_id=task_id, tenant_id=tenant_id),
            metadata=_caller_metadata("coordinator"),
        )
        assert final_response.node.status == common_pb2.TASK_STATUS_BLOCKED


@pytest.mark.asyncio
async def test_second_ready_task_with_disjoint_ownership_also_gets_assigned(
    tenant_id: str,
) -> None:
    """Sanity check that the live stack still schedules unrelated,
    non-overlapping work normally (regression guard alongside the
    overlap-specific unit tests in coordinator/tests/test_scheduler.py).
    """
    async with grpc.aio.insecure_channel(TASKGRAPH_ADDR) as channel:
        taskgraph_stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        create_response = await taskgraph_stub.CreateTaskNode(
            taskgraph_pb2.CreateTaskNodeRequest(
                node=taskgraph_pb2.TaskNode(
                    tenant_id=tenant_id,
                    title="Unrelated task",
                    description="Disjoint ownership",
                    risk_tier=common_pb2.RISK_TIER_MECHANICAL,
                    status=common_pb2.TASK_STATUS_PENDING,
                    ownership=common_pb2.OwnershipBoundary(
                        path_globs=["dashboard/app/unrelated.tsx"]
                    ),
                )
            ),
            metadata=_caller_metadata("coordinator"),
        )
        task_id = create_response.node.task_id

    async with grpc.aio.insecure_channel(COORDINATOR_ADDR) as channel:
        coordinator_stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        schedule_response = await coordinator_stub.Schedule(
            coordinator_pb2.ScheduleRequest(tenant_id=tenant_id),
            metadata=_caller_metadata("test-client"),
        )

    assigned_ids = {d.task_id for d in schedule_response.decisions}
    assert task_id in assigned_ids


def apply_migrations() -> None:
    """Convenience helper (not a test) to apply taskgraph/state migrations
    against the compose stack's exposed postgres port. Call manually once
    after `docker compose up` and before running the tests above:

        python -c "from test_e2e_docker_compose import apply_migrations as f; f()"
    """
    for migration in (
        REPO_ROOT / "taskgraph" / "migrations" / "0001_task_nodes.sql",
        REPO_ROOT / "state" / "migrations" / "0001_state_layer.sql",
        REPO_ROOT / "observability" / "migrations" / "0001_audit_trail.sql",
    ):
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(Path(__file__).with_name("docker-compose.test.yml")),
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "aecp",
                "-d",
                "aecp",
            ],
            input=migration.read_bytes(),
            check=True,
        )
