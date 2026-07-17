"""Integration-style tests for AgentPoolServicer against real
LifecycleManager/ContextHydrator/HandoffCoordinator/AgentPool logic,
backed by in-memory fakes (see tests/fakes.py) instead of a live sandbox,
mTLS server, or State/Coordinator connection.
"""

from __future__ import annotations

import grpc
import pytest

from app.agents.v1 import agents_pb2
from app.common.v1 import common_pb2
from app.grpc_server import AgentPoolServicer
from app.handoff import HandoffCoordinator
from app.hydration import ContextHydrator
from app.lifecycle import LifecycleManager
from app.pool import AgentPool

from .fakes import AbortedRPC, FakeContext, FakeIdentityIssuer, FakeSandbox, FakeStateClient

TENANT_ID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"


def make_servicer(max_slots_per_tenant: int = 10):
    manager = LifecycleManager(
        sandbox=FakeSandbox(),
        identity_issuer=FakeIdentityIssuer(),
        session_ttl_seconds=3600,
    )
    state_client = FakeStateClient()
    hydrator = ContextHydrator(lifecycle_manager=manager, state_client=state_client)
    handoff_coordinator = HandoffCoordinator(
        lifecycle_manager=manager, hydrator=hydrator, state_client=state_client
    )
    pool = AgentPool(lifecycle_manager=manager, max_slots_per_tenant=max_slots_per_tenant)
    servicer = AgentPoolServicer(
        lifecycle_manager=manager,
        hydrator=hydrator,
        handoff_coordinator=handoff_coordinator,
        pool=pool,
    )
    return servicer, manager, pool


def make_spawn_request(
    *,
    tenant_id: str = TENANT_ID,
    task_id: str = TASK_ID,
    risk_tier=common_pb2.RISK_TIER_LOCAL,
    path_globs: list[str] | None = None,
) -> agents_pb2.SpawnSessionRequest:
    return agents_pb2.SpawnSessionRequest(
        tenant_id=tenant_id,
        task_id=task_id,
        granted_risk_tier=risk_tier,
        ownership=common_pb2.OwnershipBoundary(path_globs=path_globs or ["agents/app/**"]),
        task_node_snapshot=b"opaque-task-node-bytes",
    )


async def test_spawn_session_round_trips() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    response = await servicer.SpawnSession(make_spawn_request(), context)

    assert response.session.session_id
    assert response.session.tenant_id == TENANT_ID
    assert response.session.task_id == TASK_ID
    assert response.session.granted_risk_tier == common_pb2.RISK_TIER_LOCAL
    assert response.session.status == agents_pb2.AGENT_SESSION_STATUS_ACTIVE
    assert list(response.session.ownership.path_globs) == ["agents/app/**"]
    assert response.session.task_node_snapshot == b"opaque-task-node-bytes"


async def test_spawn_session_requires_explicit_risk_tier() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.SpawnSession(
            make_spawn_request(risk_tier=common_pb2.RISK_TIER_UNSPECIFIED), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_spawn_session_rejects_when_pool_at_capacity() -> None:
    servicer, _manager, _pool = make_servicer(max_slots_per_tenant=1)
    context = FakeContext()

    await servicer.SpawnSession(make_spawn_request(task_id="task-1"), context)

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.SpawnSession(make_spawn_request(task_id="task-2"), context)

    assert exc_info.value.code == grpc.StatusCode.RESOURCE_EXHAUSTED


async def test_terminate_session_releases_pool_slot() -> None:
    servicer, _manager, pool = make_servicer(max_slots_per_tenant=1)
    context = FakeContext()

    spawn_response = await servicer.SpawnSession(make_spawn_request(), context)
    session_id = spawn_response.session.session_id

    terminate_response = await servicer.TerminateSession(
        agents_pb2.TerminateSessionRequest(session_id=session_id, reason="done"), context
    )
    assert terminate_response.terminated is True

    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 0

    # Slot freed up: a second spawn now succeeds even at max_slots=1.
    await servicer.SpawnSession(make_spawn_request(task_id="task-2"), context)


async def test_terminate_unknown_session_returns_false_not_error() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    response = await servicer.TerminateSession(
        agents_pb2.TerminateSessionRequest(session_id="does-not-exist", reason="n/a"), context
    )
    assert response.terminated is False


async def test_hydrate_context_returns_serialized_bundle() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    spawn_response = await servicer.SpawnSession(make_spawn_request(), context)
    session_id = spawn_response.session.session_id

    response = await servicer.HydrateContext(
        agents_pb2.HydrateContextRequest(session_id=session_id), context
    )

    bundle = agents_pb2.ContextBundle()
    bundle.ParseFromString(response.context_bundle)
    assert bundle.task_id == TASK_ID
    assert bundle.task_node == b"opaque-task-node-bytes"


async def test_hydrate_context_unknown_session_is_not_found() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.HydrateContext(
            agents_pb2.HydrateContextRequest(session_id="does-not-exist"), context
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


async def test_handoff_session_spawns_replacement_for_same_task() -> None:
    servicer, manager, _pool = make_servicer()
    context = FakeContext()

    spawn_response = await servicer.SpawnSession(make_spawn_request(), context)
    old_session_id = spawn_response.session.session_id

    response = await servicer.HandoffSession(
        agents_pb2.HandoffSessionRequest(session_id=old_session_id, reason="reaped"),
        context,
    )

    assert response.new_session.session_id != old_session_id
    assert response.new_session.task_id == TASK_ID
    assert await manager.get(old_session_id) is None


async def test_handoff_unknown_session_is_not_found() -> None:
    servicer, _manager, _pool = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.HandoffSession(
            agents_pb2.HandoffSessionRequest(session_id="does-not-exist", reason="n/a"),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND
