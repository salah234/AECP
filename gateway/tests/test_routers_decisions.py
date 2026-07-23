from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.common.v1 import common_pb2
from app.state.v1 import state_pb2

from .conftest import TEST_TENANT_ID


def _entry(**overrides) -> state_pb2.DecisionLogEntry:
    defaults = dict(
        entry_id="entry-1",
        tenant_id=TEST_TENANT_ID,
        task_id="task-1",
        summary="Added retry logic",
        rationale="Used exponential backoff.",
        decided_by=common_pb2.Actor(kind=common_pb2.Actor.KIND_AGENT, id="agent-1"),
    )
    defaults.update(overrides)
    entry = state_pb2.DecisionLogEntry(**defaults)
    entry.decided_at.FromDatetime(datetime.now(timezone.utc))
    return entry


def test_list_decisions_returns_serialized_entries(authed_client, fake_clients):
    entry = _entry()
    fake_clients._state.ListDecisions = AsyncMock(
        return_value=state_pb2.ListDecisionsResponse(entries=[entry])
    )

    response = authed_client.get("/api/v1/decisions")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "entryId": "entry-1",
            "taskId": "task-1",
            "summary": "Added retry logic",
            "rationale": "Used exponential backoff.",
            "decidedByKind": "KIND_AGENT",
            "decidedById": "agent-1",
        }
    ]

    called_request = fake_clients._state.ListDecisions.call_args.args[0]
    assert called_request.tenant_id == TEST_TENANT_ID
    assert called_request.task_id == ""


def test_list_decisions_passes_task_id_filter_through(authed_client, fake_clients):
    fake_clients._state.ListDecisions = AsyncMock(
        return_value=state_pb2.ListDecisionsResponse(entries=[])
    )

    response = authed_client.get("/api/v1/decisions", params={"task_id": "task-42"})

    assert response.status_code == 200
    assert response.json() == []

    called_request = fake_clients._state.ListDecisions.call_args.args[0]
    assert called_request.task_id == "task-42"


def test_list_decisions_requires_auth(client):
    response = client.get("/api/v1/decisions")

    assert response.status_code == 401
