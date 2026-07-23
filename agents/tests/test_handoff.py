"""Tests for HandoffCoordinator: terminate the old session, record the
handoff decision, spawn a replacement for the same task with no loss of
continuity.
"""

from __future__ import annotations

import pytest

from app.common.v1 import common_pb2
from app.handoff import HandoffCoordinator
from app.hydration import ContextHydrator
from app.lifecycle import LifecycleManager

from .fakes import FakeExecutor, FakeIdentityIssuer, FakeSandbox, FakeStateClient

TENANT_ID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"


def make_handoff_coordinator(executor=None):
    manager = LifecycleManager(
        sandbox=FakeSandbox(),
        identity_issuer=FakeIdentityIssuer(),
        session_ttl_seconds=3600,
    )
    state_client = FakeStateClient()
    hydrator = ContextHydrator(lifecycle_manager=manager, state_client=state_client)
    coordinator = HandoffCoordinator(
        lifecycle_manager=manager, hydrator=hydrator, state_client=state_client, executor=executor
    )
    return coordinator, manager, state_client


async def test_handoff_terminates_old_and_spawns_replacement_for_same_task() -> None:
    coordinator, manager, state_client = make_handoff_coordinator()

    ownership = common_pb2.OwnershipBoundary(path_globs=["agents/app/**"])
    old_session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_STRUCTURAL",
        ownership_globs=list(ownership.path_globs),
        ownership_boundary=ownership.SerializeToString(),
        task_node_snapshot=b"snapshot-bytes",
    )

    new_session = await coordinator.handoff(old_session.session_id, reason="agent timed out")

    assert new_session.session_id != old_session.session_id
    assert new_session.tenant_id == TENANT_ID
    assert new_session.task_id == TASK_ID
    assert new_session.granted_risk_tier == "RISK_TIER_STRUCTURAL"
    assert new_session.ownership_boundary == ownership.SerializeToString()
    assert new_session.task_node_snapshot == b"snapshot-bytes"

    # Old session is gone; a replacement rehydrates fresh rather than
    # reusing it.
    assert await manager.get(old_session.session_id) is None
    assert await manager.get(new_session.session_id) == new_session

    assert len(state_client.recorded_decisions) == 1
    decision = state_client.recorded_decisions[0]
    assert decision["tenant_id"] == TENANT_ID
    assert decision["task_id"] == TASK_ID
    assert decision["rationale"] == "agent timed out"


async def test_handoff_starts_execution_for_replacement_when_executor_wired() -> None:
    executor = FakeExecutor()
    coordinator, manager, _state_client = make_handoff_coordinator(executor=executor)

    ownership = common_pb2.OwnershipBoundary(path_globs=["agents/app/**"])
    old_session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=list(ownership.path_globs),
        ownership_boundary=ownership.SerializeToString(),
        task_node_snapshot=b"snapshot-bytes",
    )

    new_session = await coordinator.handoff(old_session.session_id, reason="agent timed out")

    handle = await manager.get_sandbox_handle(new_session.session_id)
    assert executor.spawn_background_calls == [(new_session.session_id, handle.scratch_dir)]


async def test_handoff_unknown_session_raises_lookup_error() -> None:
    coordinator, _manager, _state_client = make_handoff_coordinator()

    with pytest.raises(LookupError):
        await coordinator.handoff("does-not-exist", reason="n/a")


async def test_handoff_still_spawns_replacement_when_state_is_unreachable() -> None:
    """Regression test: a real State outage (e.g. RecordDecision failing
    with an unrelated error, as happened live when entry_id wasn't set)
    must never leave a task with no agent session at all. The old session
    is already atomically gone by the time record_decision runs (see
    handoff.py's docstring), so the replacement must exist regardless of
    whether the decision-log write succeeds.
    """
    manager = LifecycleManager(
        sandbox=FakeSandbox(),
        identity_issuer=FakeIdentityIssuer(),
        session_ttl_seconds=3600,
    )
    state_client = FakeStateClient(fail_record_decision=True)
    hydrator = ContextHydrator(lifecycle_manager=manager, state_client=state_client)
    coordinator = HandoffCoordinator(
        lifecycle_manager=manager, hydrator=hydrator, state_client=state_client
    )

    old_session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    # Must not raise, even though record_decision blows up internally.
    new_session = await coordinator.handoff(old_session.session_id, reason="agent timed out")

    assert new_session.session_id != old_session.session_id
    assert new_session.task_id == TASK_ID
    assert await manager.get(new_session.session_id) == new_session
    assert state_client.recorded_decisions == []
