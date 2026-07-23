"""Confirms every endpoint with no backing upstream RPC returns a
deliberate 501 (never a fake empty list) — see the gateway architecture
plan's scope decision. GET /api/v1/decisions,
/api/v1/decisions/contracts/{id}, and GET /api/v1/agents all have real
backing RPCs now (StateService.ListDecisions/GetInterfaceContract,
CoordinatorService.ListAgentSessions) — see test_routers_decisions.py and
test_routers_agents.py for their happy-path coverage; this file keeps
their still-requires-auth case (auth applies regardless of whether an
endpoint is gapped) and the GetInterfaceContract check below, which
predates ListDecisions and hasn't moved.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.state.v1 import state_pb2


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/escalations"),
        ("POST", "/api/v1/escalations/some-task/approve"),
        ("POST", "/api/v1/escalations/some-task/reject"),
        ("GET", "/api/v1/escalations/conflicts"),
        ("GET", "/api/v1/escalations/drift"),
        ("GET", "/api/v1/agents/some-session"),
        ("POST", "/api/v1/agents/some-session/terminate"),
    ],
)
def test_gapped_endpoints_return_501(authed_client, method, path):
    response = authed_client.request(method, path)

    assert response.status_code == 501
    assert "detail" in response.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/decisions",
        "/api/v1/agents",
    ],
)
def test_gapped_endpoints_still_require_auth(client, path):
    response = client.get(path)

    assert response.status_code == 401


def test_get_interface_contract_happy_path(authed_client, fake_clients):
    contract = state_pb2.InterfaceContract(
        contract_id="contract-1", name="TaskNode v1", schema="{}", version=1, frozen=True
    )
    fake_clients._state.GetInterfaceContract = AsyncMock(
        return_value=state_pb2.GetInterfaceContractResponse(contract=contract)
    )

    response = authed_client.get("/api/v1/decisions/contracts/contract-1")

    assert response.status_code == 200
    assert response.json() == {
        "contractId": "contract-1",
        "name": "TaskNode v1",
        "schema": "{}",
        "version": 1,
        "frozen": True,
    }
