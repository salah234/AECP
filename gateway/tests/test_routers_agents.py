from __future__ import annotations

from unittest.mock import AsyncMock

from app.agents.v1 import agents_pb2
from app.coordinator.v1 import coordinator_pb2

from .conftest import TEST_TENANT_ID


def _session(**overrides) -> agents_pb2.AgentSession:
    defaults = dict(
        session_id="session-1",
        tenant_id=TEST_TENANT_ID,
        task_id="task-1",
        status=agents_pb2.AGENT_SESSION_STATUS_ACTIVE,
    )
    defaults.update(overrides)
    return agents_pb2.AgentSession(**defaults)


def test_list_sessions_returns_serialized_sessions(authed_client, fake_clients):
    session = _session()
    fake_clients._coordinator.ListAgentSessions = AsyncMock(
        return_value=coordinator_pb2.ListAgentSessionsResponse(sessions=[session])
    )

    response = authed_client.get("/api/v1/agents")

    assert response.status_code == 200
    assert response.json() == [
        {"sessionId": "session-1", "taskId": "task-1", "status": "active"}
    ]

    called_request = fake_clients._coordinator.ListAgentSessions.call_args.args[0]
    assert called_request.tenant_id == TEST_TENANT_ID


def test_list_sessions_requires_auth(client):
    response = client.get("/api/v1/agents")

    assert response.status_code == 401


def test_get_session_still_returns_501(authed_client):
    response = authed_client.get("/api/v1/agents/session-1")

    assert response.status_code == 501


def test_terminate_session_still_returns_501(authed_client):
    response = authed_client.post("/api/v1/agents/session-1/terminate")

    assert response.status_code == 501
