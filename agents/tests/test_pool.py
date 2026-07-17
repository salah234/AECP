"""Tests for AgentPool capacity accounting, including the concurrent
acquire race the design note in pool.py calls out.
"""

from __future__ import annotations

import asyncio

from app.lifecycle import LifecycleManager
from app.pool import AgentPool

from .fakes import FakeIdentityIssuer, FakeSandbox

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def make_pool(max_slots=2):
    manager = LifecycleManager(
        sandbox=FakeSandbox(),
        identity_issuer=FakeIdentityIssuer(),
        session_ttl_seconds=3600,
    )
    return AgentPool(lifecycle_manager=manager, max_slots_per_tenant=max_slots), manager


async def test_acquire_slot_respects_max_and_release_frees_it() -> None:
    pool, _manager = make_pool(max_slots=1)

    assert await pool.acquire_slot(TENANT_ID) is True
    assert await pool.acquire_slot(TENANT_ID) is False

    capacity = await pool.capacity(TENANT_ID)
    assert capacity.total_slots == 1
    assert capacity.in_use_slots == 1

    await pool.release_slot(TENANT_ID)
    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 0

    assert await pool.acquire_slot(TENANT_ID) is True


async def test_release_slot_below_zero_is_a_noop() -> None:
    pool, _manager = make_pool(max_slots=1)

    await pool.release_slot(TENANT_ID)

    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 0


async def test_concurrent_acquire_never_exceeds_max_slots() -> None:
    """Two agents' worth of concurrent SpawnSession calls racing for the
    same tenant's capacity must never both succeed past the configured
    max — this is the capacity-accounting analogue of CLAUDE.md's
    concurrent-agent scheduling invariant.
    """
    pool, _manager = make_pool(max_slots=3)

    results = await asyncio.gather(*(pool.acquire_slot(TENANT_ID) for _ in range(10)))

    assert sum(results) == 3
    capacity = await pool.capacity(TENANT_ID)
    assert capacity.in_use_slots == 3


async def test_reconcile_resyncs_from_lifecycle_manager() -> None:
    pool, manager = make_pool(max_slots=5)

    await manager.spawn(
        tenant_id=TENANT_ID,
        task_id="t1",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )
    await manager.spawn(
        tenant_id=TENANT_ID,
        task_id="t2",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    capacity = await pool.reconcile(TENANT_ID)
    assert capacity.in_use_slots == 2
