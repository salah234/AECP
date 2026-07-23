from __future__ import annotations

from unittest.mock import AsyncMock

import grpc

from app.common.v1 import common_pb2
from app.coordinator.v1 import coordinator_pb2

from .conftest import TEST_TENANT_ID


def _decision(**overrides) -> coordinator_pb2.AssignmentDecision:
    defaults = dict(
        task_id="task-1",
        agent_id="session-1",
        granted_risk_tier=common_pb2.RISK_TIER_LOCAL,
        rationale="only ready task for this tenant",
    )
    defaults.update(overrides)
    return coordinator_pb2.AssignmentDecision(**defaults)


def test_schedule_returns_serialized_decisions_and_trace_id(authed_client, fake_clients):
    fake_clients._coordinator.Schedule = AsyncMock(
        return_value=coordinator_pb2.ScheduleResponse(decisions=[_decision()])
    )

    response = authed_client.post("/api/v1/coordinator/schedule")

    assert response.status_code == 200
    body = response.json()
    assert body["decisions"] == [
        {
            "taskId": "task-1",
            "agentId": "session-1",
            "grantedRiskTier": "local",
            "rationale": "only ready task for this tenant",
        }
    ]
    # No tracer provider is installed in this fast unit suite (main.py's
    # real lifespan, which calls init_tracing, is bypassed by the `client`
    # fixture — see conftest.py), so there is no active span and
    # current_trace_id_hex() correctly reports "" rather than a fake id.
    assert body["traceId"] == ""

    called_request = fake_clients._coordinator.Schedule.call_args.args[0]
    assert called_request.tenant_id == TEST_TENANT_ID


def test_schedule_returns_empty_decisions_when_nothing_ready(authed_client, fake_clients):
    fake_clients._coordinator.Schedule = AsyncMock(
        return_value=coordinator_pb2.ScheduleResponse(decisions=[])
    )

    response = authed_client.post("/api/v1/coordinator/schedule")

    assert response.status_code == 200
    assert response.json()["decisions"] == []


def test_schedule_requires_auth(client):
    response = client.post("/api/v1/coordinator/schedule")

    assert response.status_code == 401


def test_schedule_maps_grpc_error_to_http(authed_client, fake_clients):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE,
        initial_metadata=grpc.aio.Metadata(),
        trailing_metadata=grpc.aio.Metadata(),
        details="coordinator unreachable",
    )
    fake_clients._coordinator.Schedule = AsyncMock(side_effect=error)

    response = authed_client.post("/api/v1/coordinator/schedule")

    assert response.status_code == 503
    assert response.json()["detail"] == "coordinator unreachable"
