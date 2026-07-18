from __future__ import annotations

import pytest

from app.common.v1 import common_pb2
from app.tradeoff import TradeoffResolver
from tests.fakes import FakeAuditClient, FakeStateClient, FakeTaskGraphClient, make_task_node


@pytest.mark.asyncio
async def test_escalation_to_mechanical_tier_auto_approved() -> None:
    node = make_task_node()
    taskgraph_client = FakeTaskGraphClient([node])
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), taskgraph_client)

    decision = await resolver.escalate(
        task_id=node.task_id,
        tenant_id=node.tenant_id,
        agent_id="session-1",
        reason="turned out simpler than expected",
        requested_risk_tier=common_pb2.RISK_TIER_MECHANICAL,
    )

    assert decision.approved is True
    assert decision.decided_by == "coordinator"


@pytest.mark.asyncio
async def test_escalation_to_local_tier_auto_approved() -> None:
    node = make_task_node()
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), FakeTaskGraphClient([node]))

    decision = await resolver.escalate(
        task_id=node.task_id,
        tenant_id=node.tenant_id,
        agent_id="session-1",
        reason="reason",
        requested_risk_tier=common_pb2.RISK_TIER_LOCAL,
    )

    assert decision.approved is True


@pytest.mark.parametrize(
    "tier", [common_pb2.RISK_TIER_STRUCTURAL, common_pb2.RISK_TIER_ARCHITECTURAL]
)
@pytest.mark.asyncio
async def test_escalation_to_structural_or_architectural_always_routes_to_human(tier) -> None:
    node = make_task_node()
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), FakeTaskGraphClient([node]))

    decision = await resolver.escalate(
        task_id=node.task_id,
        tenant_id=node.tenant_id,
        agent_id="session-1",
        reason="this needs a bigger blast radius than I was granted",
        requested_risk_tier=tier,
    )

    assert decision.approved is False
    assert decision.decided_by == "human"


@pytest.mark.asyncio
async def test_escalation_requires_explicit_risk_tier() -> None:
    node = make_task_node()
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), FakeTaskGraphClient([node]))

    with pytest.raises(ValueError):
        await resolver.escalate(
            task_id=node.task_id,
            tenant_id=node.tenant_id,
            agent_id="session-1",
            reason="reason",
            requested_risk_tier=common_pb2.RISK_TIER_UNSPECIFIED,
        )


@pytest.mark.asyncio
async def test_escalation_is_always_audited_as_security_relevant() -> None:
    node = make_task_node()
    audit_client = FakeAuditClient()
    resolver = TradeoffResolver(FakeStateClient(), audit_client, FakeTaskGraphClient([node]))

    await resolver.escalate(
        task_id=node.task_id,
        tenant_id=node.tenant_id,
        agent_id="session-1",
        reason="reason",
        requested_risk_tier=common_pb2.RISK_TIER_ARCHITECTURAL,
    )

    assert len(audit_client.recorded_events) == 1
    assert audit_client.recorded_events[0]["security_relevant"] is True
    assert audit_client.recorded_events[0]["action"] == "escalate"


@pytest.mark.asyncio
async def test_escalate_unknown_task_raises() -> None:
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), FakeTaskGraphClient([]))

    with pytest.raises(ValueError):
        await resolver.escalate(
            task_id="missing",
            tenant_id="tenant-1",
            agent_id="session-1",
            reason="reason",
            requested_risk_tier=common_pb2.RISK_TIER_LOCAL,
        )


@pytest.mark.asyncio
async def test_report_blocker_marks_task_blocked() -> None:
    node = make_task_node()
    taskgraph_client = FakeTaskGraphClient([node])
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), taskgraph_client)

    await resolver.report_blocker(node.task_id, node.tenant_id, "session-1", "hit a missing dependency")

    assert len(taskgraph_client.status_updates) == 1
    _task_id, status, _reason = taskgraph_client.status_updates[0]
    assert status == common_pb2.TASK_STATUS_BLOCKED


@pytest.mark.asyncio
async def test_report_blocker_unknown_task_raises() -> None:
    resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), FakeTaskGraphClient([]))

    with pytest.raises(ValueError):
        await resolver.report_blocker("missing", "tenant-1", "session-1", "description")


@pytest.mark.asyncio
async def test_report_blocker_is_audited_as_not_security_relevant() -> None:
    node = make_task_node()
    audit_client = FakeAuditClient()
    resolver = TradeoffResolver(FakeStateClient(), audit_client, FakeTaskGraphClient([node]))

    await resolver.report_blocker(node.task_id, node.tenant_id, "session-1", "description")

    assert len(audit_client.recorded_events) == 1
    assert audit_client.recorded_events[0]["security_relevant"] is False
