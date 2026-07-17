"""Tests for LifecycleManager: spawn/terminate/reap_expired against fake
Sandbox and CredentialIssuer, no real filesystem or network calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.lifecycle import LifecycleManager

from .fakes import FakeIdentityIssuer, FakeSandbox

TENANT_ID = "11111111-1111-1111-1111-111111111111"
TASK_ID = "22222222-2222-2222-2222-222222222222"


def make_manager(now_fn=None, ttl=3600):
    sandbox = FakeSandbox()
    identity_issuer = FakeIdentityIssuer()
    manager = LifecycleManager(
        sandbox=sandbox,
        identity_issuer=identity_issuer,
        session_ttl_seconds=ttl,
        **({"now_fn": now_fn} if now_fn is not None else {}),
    )
    return manager, sandbox, identity_issuer


async def test_spawn_creates_sandbox_and_issues_credential() -> None:
    manager, sandbox, identity_issuer = make_manager()

    session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=["agents/app/**"],
        ownership_boundary=b"boundary-bytes",
        task_node_snapshot=b"task-node-bytes",
    )

    assert session.tenant_id == TENANT_ID
    assert session.task_id == TASK_ID
    assert session.granted_risk_tier == "RISK_TIER_LOCAL"
    assert sandbox.created[session.session_id] == ["agents/app/**"]
    assert identity_issuer.issued[session.session_id] == 3600

    fetched = await manager.get(session.session_id)
    assert fetched == session


async def test_terminate_destroys_sandbox_and_revokes_credential() -> None:
    manager, sandbox, identity_issuer = make_manager()

    session = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id=TASK_ID,
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    await manager.terminate(session.session_id, reason="done")

    assert session.session_id in sandbox.destroyed
    assert session.session_id in identity_issuer.revoked
    assert await manager.get(session.session_id) is None


async def test_terminate_unknown_session_is_a_noop() -> None:
    manager, sandbox, identity_issuer = make_manager()

    await manager.terminate("does-not-exist", reason="n/a")

    assert sandbox.destroyed == []
    assert identity_issuer.revoked == []


async def test_reap_expired_terminates_only_past_ttl_sessions() -> None:
    clock = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    manager, sandbox, _identity_issuer = make_manager(
        now_fn=lambda: clock["now"], ttl=60
    )

    fresh = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id="fresh-task",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    clock["now"] += timedelta(seconds=30)
    stale = await manager.spawn(
        tenant_id=TENANT_ID,
        task_id="stale-task",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    # fresh expires at +60s, stale expires at +90s (spawned at +30s with a
    # 60s ttl). Advancing to +65s puts only `fresh` past its TTL.
    clock["now"] = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=65)

    expired = await manager.reap_expired()

    assert {s.session_id for s in expired} == {fresh.session_id}
    assert await manager.get(fresh.session_id) is None
    assert await manager.get(stale.session_id) == stale
    assert fresh.session_id in sandbox.destroyed


async def test_count_active_scopes_by_tenant() -> None:
    manager, _sandbox, _identity_issuer = make_manager()

    await manager.spawn(
        tenant_id=TENANT_ID,
        task_id="t1",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )
    await manager.spawn(
        tenant_id="other-tenant",
        task_id="t2",
        granted_risk_tier="RISK_TIER_LOCAL",
        ownership_globs=[],
        ownership_boundary=b"",
        task_node_snapshot=b"",
    )

    assert await manager.count_active(TENANT_ID) == 1
    assert await manager.count_active("other-tenant") == 1
    assert await manager.count_active("no-sessions") == 0
