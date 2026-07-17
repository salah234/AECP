"""CLAUDE.md requires scheduling/conflict logic to be tested with at
least two concurrent agents (see coordinator/tests/test_concurrent_agents.py,
integration/tests/test_concurrent_agents.py). Agent Pool isn't itself a
scheduler, but it is exactly the component multiple concurrent agent
sessions actually exercise, so it carries the same spirit of test:
concurrent SpawnSession/TerminateSession/reap_expired calls must never
double-spawn past capacity, double-terminate, or corrupt the session
registry.
"""

from __future__ import annotations

import asyncio

import grpc

from app.agents.v1 import agents_pb2
from app.common.v1 import common_pb2
from app.grpc_server import AgentPoolServicer
from app.handoff import HandoffCoordinator
from app.hydration import ContextHydrator
from app.lifecycle import LifecycleManager
from app.pool import AgentPool

from .fakes import AbortedRPC, FakeContext, FakeIdentityIssuer, FakeSandbox, FakeStateClient

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def make_servicer(max_slots_per_tenant: int):
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


def make_spawn_request(task_id: str) -> agents_pb2.SpawnSessionRequest:
    return agents_pb2.SpawnSessionRequest(
        tenant_id=TENANT_ID,
        task_id=task_id,
        granted_risk_tier=common_pb2.RISK_TIER_LOCAL,
        ownership=common_pb2.OwnershipBoundary(path_globs=[f"agents/app/{task_id}/**"]),
        task_node_snapshot=b"",
    )


async def _try_spawn(servicer, task_id: str):
    context = FakeContext()
    try:
        return await servicer.SpawnSession(make_spawn_request(task_id), context)
    except AbortedRPC as exc:
        return exc


async def test_concurrent_spawns_never_exceed_pool_capacity() -> None:
    """Ten concurrent agents racing to spawn against a 3-slot tenant pool
    must result in exactly 3 active sessions, not 10 (overcommit) or a
    corrupted/racy count.
    """
    servicer, manager, pool = make_servicer(max_slots_per_tenant=3)

    results = await asyncio.gather(
        *(_try_spawn(servicer, f"task-{i}") for i in range(10))
    )

    succeeded = [r for r in results if not isinstance(r, AbortedRPC)]
    rejected = [r for r in results if isinstance(r, AbortedRPC)]

    assert len(succeeded) == 3
    assert len(rejected) == 7
    assert all(r.code == grpc.StatusCode.RESOURCE_EXHAUSTED for r in rejected)

    assert await manager.count_active(TENANT_ID) == 3
    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 3


async def test_concurrent_terminate_of_same_session_only_releases_slot_once() -> None:
    """Two concurrent agents both trying to terminate the same session
    (e.g. a duplicate TerminateSession retry racing a Coordinator-driven
    one) must not release the pool slot twice, which would let a future
    spawn overcommit capacity.
    """
    servicer, manager, pool = make_servicer(max_slots_per_tenant=1)
    context = FakeContext()

    spawn_response = await servicer.SpawnSession(make_spawn_request("task-1"), context)
    session_id = spawn_response.session.session_id

    async def terminate():
        return await servicer.TerminateSession(
            agents_pb2.TerminateSessionRequest(session_id=session_id, reason="race"),
            FakeContext(),
        )

    results = await asyncio.gather(terminate(), terminate())

    assert sum(1 for r in results if r.terminated) == 1
    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 0
    assert await manager.get(session_id) is None


async def test_concurrent_handoffs_of_same_session_only_one_succeeds() -> None:
    """Two concurrent handoff requests for the same session (e.g. a
    reap-triggered handoff racing an explicit agent-requested one) must
    not both succeed and spawn two replacement sessions for one task.
    """
    servicer, manager, _pool = make_servicer(max_slots_per_tenant=10)
    context = FakeContext()

    spawn_response = await servicer.SpawnSession(make_spawn_request("task-1"), context)
    session_id = spawn_response.session.session_id

    async def handoff():
        try:
            return await servicer.HandoffSession(
                agents_pb2.HandoffSessionRequest(session_id=session_id, reason="race"),
                FakeContext(),
            )
        except AbortedRPC as exc:
            return exc

    results = await asyncio.gather(handoff(), handoff())

    succeeded = [r for r in results if not isinstance(r, AbortedRPC)]
    failed = [r for r in results if isinstance(r, AbortedRPC)]

    # Exactly one handoff wins the race and spawns a replacement; the
    # other finds the session already gone.
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert failed[0].code == grpc.StatusCode.NOT_FOUND
    assert await manager.count_active(TENANT_ID) == 1
