from __future__ import annotations

from unittest.mock import AsyncMock

from app.common.v1 import common_pb2
from app.taskgraph.v1 import taskgraph_pb2


def _task_node(**overrides) -> taskgraph_pb2.TaskNode:
    defaults = dict(
        task_id="22222222-2222-2222-2222-222222222222",
        tenant_id="11111111-1111-1111-1111-111111111111",
        title="Add retry to webhook sender",
        description="",
        risk_tier=common_pb2.RISK_TIER_LOCAL,
        status=common_pb2.TASK_STATUS_PENDING,
    )
    defaults.update(overrides)
    return taskgraph_pb2.TaskNode(**defaults)


def test_list_ready_tasks_returns_serialized_nodes(authed_client, fake_clients):
    node = _task_node()
    fake_clients._taskgraph.ListReadyTaskNodes = AsyncMock(
        return_value=taskgraph_pb2.ListReadyTaskNodesResponse(nodes=[node])
    )

    response = authed_client.get("/api/v1/tasks")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "taskId": node.task_id,
            "title": node.title,
            "description": node.description,
            "status": "pending",
            "riskTier": "local",
            "dependsOnTaskIds": [],
            "blocksTaskIds": [],
            "assignedAgentId": "",
        }
    ]

    called_request = fake_clients._taskgraph.ListReadyTaskNodes.call_args.args[0]
    assert called_request.tenant_id == "11111111-1111-1111-1111-111111111111"


def test_list_ready_tasks_requires_auth(client):
    response = client.get("/api/v1/tasks")

    assert response.status_code == 401


def test_get_task_translates_not_found_to_404(authed_client, fake_clients):
    import grpc

    async def raise_not_found(*args, **kwargs):
        raise grpc.aio.AioRpcError(grpc.StatusCode.NOT_FOUND, grpc.aio.Metadata(), grpc.aio.Metadata())

    fake_clients._taskgraph.GetTaskNode = raise_not_found

    response = authed_client.get("/api/v1/tasks/does-not-exist")

    assert response.status_code == 404


def test_create_task_builds_a_pending_node_with_generated_id(authed_client, fake_clients):
    captured = {}

    async def fake_create(request, **kwargs):
        captured["node"] = request.node
        return taskgraph_pb2.CreateTaskNodeResponse(node=request.node)

    fake_clients._taskgraph.CreateTaskNode = fake_create

    response = authed_client.post(
        "/api/v1/tasks",
        json={
            "title": "New task",
            "risk_tier": "local",
            "path_globs": ["services/webhooks/**"],
        },
    )

    assert response.status_code == 200
    node = captured["node"]
    assert node.title == "New task"
    assert node.status == common_pb2.TASK_STATUS_PENDING
    assert node.risk_tier == common_pb2.RISK_TIER_LOCAL
    assert node.tenant_id == "11111111-1111-1111-1111-111111111111"
    assert node.task_id  # generated, non-empty
    assert list(node.ownership.path_globs) == ["services/webhooks/**"]


def test_create_task_rejects_unknown_risk_tier(authed_client, fake_clients):
    response = authed_client.post(
        "/api/v1/tasks", json={"title": "New task", "risk_tier": "not-a-real-tier"}
    )

    assert response.status_code == 400


def test_update_task_status_rejects_unknown_status(authed_client, fake_clients):
    response = authed_client.post(
        "/api/v1/tasks/22222222-2222-2222-2222-222222222222/status",
        json={"status": "not-a-real-status"},
    )

    assert response.status_code == 400


def test_update_task_status_happy_path(authed_client, fake_clients):
    updated = _task_node(status=common_pb2.TASK_STATUS_IN_PROGRESS)
    fake_clients._taskgraph.UpdateTaskStatus = AsyncMock(
        return_value=taskgraph_pb2.UpdateTaskStatusResponse(node=updated)
    )

    response = authed_client.post(
        "/api/v1/tasks/22222222-2222-2222-2222-222222222222/status",
        json={"status": "in_progress", "reason": "started work"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
