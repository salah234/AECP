"""Tests for ContextHydrator against a real LifecycleManager (backed by
fakes) — no gRPC, no live State connection.
"""

from __future__ import annotations

import pytest

from app.hydration import ContextHydrator
from app.lifecycle import LifecycleManager

from .fakes import FakeIdentityIssuer, FakeSandbox, FakeStateClient

TENANT_ID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"


def make_hydrator():
    manager = LifecycleManager(
        sandbox=FakeSandbox(),
        identity_issuer=FakeIdentityIssuer(),
        session_ttl_seconds=3600,
    )
    state_client = FakeStateClient()
    return ContextHydrator(lifecycle_manager=manager, state_client=state_client), manager


async def test_hydrate_returns_bundle_captured_at_spawn_time() -> None:
    hydrator, manager = make_hydrator()

    session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=["agents/app/**"],
        ownership_boundary=b"serialized-ownership",
        task_node_snapshot=b"serialized-task-node",
    )

    bundle = await hydrator.hydrate(session.session_id)

    assert bundle.task_id == TASK_ID
    assert bundle.task_node == b"serialized-task-node"
    assert bundle.ownership_boundary == b"serialized-ownership"
    # Documented contract gap: StateService has no query-by-task RPC yet.
    assert bundle.relevant_interface_contracts == []
    assert bundle.relevant_decision_log_entries == []


async def test_hydrate_unknown_session_raises_lookup_error() -> None:
    hydrator, _manager = make_hydrator()

    with pytest.raises(LookupError):
        await hydrator.hydrate("does-not-exist")
