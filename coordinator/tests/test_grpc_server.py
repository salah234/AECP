from __future__ import annotations

import pytest

from app.assignment import AssignmentEngine
from app.common.v1 import common_pb2
from app.coordinator.v1 import coordinator_pb2
from app.grpc_server import CoordinatorServicer
from app.scheduler import Scheduler
from app.tradeoff import TradeoffResolver
from tests.fakes import (
    AbortedRPC,
    FakeAgentPoolClient,
    FakeAuditClient,
    FakeContext,
    FakeStateClient,
    FakeTaskGraphClient,
    make_task_node,
)


def _build_servicer(taskgraph_client, *, integration_client=None, agent_pool_client=None):
    agent_pool_client = agent_pool_client or FakeAgentPoolClient()
    scheduler = Scheduler(taskgraph_client, integration_client)
    assignment_engine = AssignmentEngine(agent_pool_client, FakeStateClient(), taskgraph_client)
    tradeoff_resolver = TradeoffResolver(FakeStateClient(), FakeAuditClient(), taskgraph_client)
    return CoordinatorServicer(scheduler, assignment_engine, tradeoff_resolver, agent_pool_client)


@pytest.mark.asyncio
async def test_schedule_returns_assignment_decisions() -> None:
    node = make_task_node(tenant_id="tenant-1")
    servicer = _build_servicer(FakeTaskGraphClient([node]))

    response = await servicer.Schedule(
        coordinator_pb2.ScheduleRequest(tenant_id="tenant-1"), FakeContext()
    )

    assert len(response.decisions) == 1
    assert response.decisions[0].task_id == node.task_id
    assert response.decisions[0].granted_risk_tier == node.risk_tier


@pytest.mark.asyncio
async def test_schedule_requires_tenant_id() -> None:
    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC):
        await servicer.Schedule(coordinator_pb2.ScheduleRequest(tenant_id=""), FakeContext())


@pytest.mark.asyncio
async def test_escalate_returns_decision() -> None:
    node = make_task_node()
    servicer = _build_servicer(FakeTaskGraphClient([node]))

    response = await servicer.Escalate(
        coordinator_pb2.EscalateRequest(
            task_id=node.task_id,
            tenant_id=node.tenant_id,
            agent_id="session-1",
            reason="reason",
            requested_risk_tier=common_pb2.RISK_TIER_MECHANICAL,
        ),
        FakeContext(),
    )

    assert response.approved is True
    assert response.decided_by == "coordinator"


@pytest.mark.asyncio
async def test_escalate_requires_task_id_agent_id_and_tenant_id() -> None:
    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC):
        await servicer.Escalate(
            coordinator_pb2.EscalateRequest(
                task_id="", agent_id="session-1", tenant_id="tenant-1"
            ),
            FakeContext(),
        )

    with pytest.raises(AbortedRPC):
        await servicer.Escalate(
            coordinator_pb2.EscalateRequest(
                task_id="task-1", agent_id="", tenant_id="tenant-1"
            ),
            FakeContext(),
        )

    with pytest.raises(AbortedRPC):
        await servicer.Escalate(
            coordinator_pb2.EscalateRequest(
                task_id="task-1", agent_id="session-1", tenant_id=""
            ),
            FakeContext(),
        )


@pytest.mark.asyncio
async def test_escalate_unknown_task_aborts_invalid_argument() -> None:
    import grpc

    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.Escalate(
            coordinator_pb2.EscalateRequest(
                task_id="missing",
                tenant_id="tenant-1",
                agent_id="session-1",
                requested_risk_tier=common_pb2.RISK_TIER_LOCAL,
            ),
            FakeContext(),
        )
    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_report_blocker_acknowledges() -> None:
    node = make_task_node()
    servicer = _build_servicer(FakeTaskGraphClient([node]))

    response = await servicer.ReportBlocker(
        coordinator_pb2.ReportBlockerRequest(
            task_id=node.task_id,
            tenant_id=node.tenant_id,
            agent_id="session-1",
            description="blocked",
        ),
        FakeContext(),
    )

    assert response.acknowledged is True


@pytest.mark.asyncio
async def test_report_blocker_requires_task_id_and_tenant_id() -> None:
    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC):
        await servicer.ReportBlocker(
            coordinator_pb2.ReportBlockerRequest(
                task_id="", agent_id="session-1", tenant_id="tenant-1"
            ),
            FakeContext(),
        )

    with pytest.raises(AbortedRPC):
        await servicer.ReportBlocker(
            coordinator_pb2.ReportBlockerRequest(
                task_id="task-1", agent_id="session-1", tenant_id=""
            ),
            FakeContext(),
        )


@pytest.mark.asyncio
async def test_report_completion_acknowledges() -> None:
    node = make_task_node()
    servicer = _build_servicer(FakeTaskGraphClient([node]))

    response = await servicer.ReportCompletion(
        coordinator_pb2.ReportCompletionRequest(
            task_id=node.task_id,
            tenant_id=node.tenant_id,
            agent_id="session-1",
            summary="Added retry logic",
            rationale="Used exponential backoff",
        ),
        FakeContext(),
    )

    assert response.acknowledged is True


@pytest.mark.asyncio
async def test_report_completion_requires_task_id_and_tenant_id() -> None:
    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC):
        await servicer.ReportCompletion(
            coordinator_pb2.ReportCompletionRequest(
                task_id="", agent_id="session-1", tenant_id="tenant-1"
            ),
            FakeContext(),
        )

    with pytest.raises(AbortedRPC):
        await servicer.ReportCompletion(
            coordinator_pb2.ReportCompletionRequest(
                task_id="task-1", agent_id="session-1", tenant_id=""
            ),
            FakeContext(),
        )


@pytest.mark.asyncio
async def test_report_completion_unknown_task_aborts_invalid_argument() -> None:
    import grpc

    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.ReportCompletion(
            coordinator_pb2.ReportCompletionRequest(
                task_id="missing",
                tenant_id="tenant-1",
                agent_id="session-1",
                summary="summary",
                rationale="rationale",
            ),
            FakeContext(),
        )
    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_list_agent_sessions_proxies_to_agent_pool_scoped_by_tenant() -> None:
    agent_pool_client = FakeAgentPoolClient()
    servicer = _build_servicer(FakeTaskGraphClient([]), agent_pool_client=agent_pool_client)

    await agent_pool_client.spawn_session(
        tenant_id="tenant-1",
        task_id="task-1",
        granted_risk_tier=common_pb2.RISK_TIER_LOCAL,
        ownership=common_pb2.OwnershipBoundary(),
        task_node_snapshot=b"",
    )
    await agent_pool_client.spawn_session(
        tenant_id="tenant-2",
        task_id="task-2",
        granted_risk_tier=common_pb2.RISK_TIER_LOCAL,
        ownership=common_pb2.OwnershipBoundary(),
        task_node_snapshot=b"",
    )

    response = await servicer.ListAgentSessions(
        coordinator_pb2.ListAgentSessionsRequest(tenant_id="tenant-1"), FakeContext()
    )

    assert [s.task_id for s in response.sessions] == ["task-1"]


@pytest.mark.asyncio
async def test_list_agent_sessions_requires_tenant_id() -> None:
    import grpc

    servicer = _build_servicer(FakeTaskGraphClient([]))

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.ListAgentSessions(
            coordinator_pb2.ListAgentSessionsRequest(tenant_id=""), FakeContext()
        )
    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
