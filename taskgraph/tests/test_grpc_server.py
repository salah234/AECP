"""Integration-style tests for TaskGraphServicer against real TaskGraph and
ownership logic, backed by an in-memory fake repository (see tests/fakes.py)
instead of Postgres.
"""

from __future__ import annotations

import grpc
import pytest

from app import ownership
from app.common.v1 import common_pb2
from app.graph import TaskGraph
from app.grpc_server import TaskGraphServicer
from app.schema import TaskStatus
from app.taskgraph.v1 import taskgraph_pb2

from .fakes import AbortedRPC, FakeContext, FakeTaskNodeRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def make_servicer() -> tuple[TaskGraphServicer, FakeTaskNodeRepository]:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)
    servicer = TaskGraphServicer(
        graph=graph,
        ownership_module=ownership,
        repository=repository,
    )
    return servicer, repository


def make_create_request(
    *,
    task_id: str = "",
    title: str = "Implement thing",
    depends_on_task_ids: list[str] | None = None,
    risk_tier=common_pb2.RISK_TIER_LOCAL,
    status=common_pb2.TASK_STATUS_UNSPECIFIED,
    path_globs: list[str] | None = None,
) -> taskgraph_pb2.CreateTaskNodeRequest:
    return taskgraph_pb2.CreateTaskNodeRequest(
        node=taskgraph_pb2.TaskNode(
            task_id=task_id,
            tenant_id=TENANT_ID,
            title=title,
            description="",
            risk_tier=risk_tier,
            status=status,
            ownership=common_pb2.OwnershipBoundary(
                path_globs=path_globs or ["taskgraph/app/**"],
            ),
            depends_on_task_ids=depends_on_task_ids or [],
            definition_of_done=taskgraph_pb2.DefinitionOfDone(
                required_checks=["pytest"],
                acceptance_criteria=["works"],
                requires_human_review_gate=True,
            ),
        )
    )


async def test_create_and_get_task_node_round_trips() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    response = await servicer.CreateTaskNode(make_create_request(title="Build the thing"), context)

    assert response.node.task_id
    assert response.node.title == "Build the thing"
    assert response.node.risk_tier == common_pb2.RISK_TIER_LOCAL
    assert response.node.status == common_pb2.TASK_STATUS_PENDING

    get_response = await servicer.GetTaskNode(
        taskgraph_pb2.GetTaskNodeRequest(task_id=response.node.task_id), context
    )
    assert get_response.node.task_id == response.node.task_id


async def test_create_task_node_requires_explicit_risk_tier() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.CreateTaskNode(
            make_create_request(risk_tier=common_pb2.RISK_TIER_UNSPECIFIED), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_create_task_node_rejects_dangling_dependency() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.CreateTaskNode(
            make_create_request(depends_on_task_ids=["does-not-exist"]), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
    assert repository._nodes == {}


async def test_create_task_node_maps_cycle_error_to_invalid_argument(monkeypatch) -> None:
    # A cycle can only ever be introduced across nodes that already exist
    # when CreateTaskNode is called (see tests/test_graph.py for the real
    # detection + rollback path exercised directly against TaskGraph); here
    # we only need to confirm the servicer maps that failure to the right
    # gRPC status.
    servicer, _repository = make_servicer()
    context = FakeContext()

    async def raise_cycle(node):
        from app.graph import CycleDetectedError

        raise CycleDetectedError("cycle!", task_id=node.task_id)

    monkeypatch.setattr(servicer.graph, "add_node", raise_cycle)

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.CreateTaskNode(make_create_request(), context)

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_get_task_node_not_found() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.GetTaskNode(taskgraph_pb2.GetTaskNodeRequest(task_id="missing"), context)

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


async def test_update_task_status_transitions_and_persists() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    created = await servicer.CreateTaskNode(make_create_request(), context)

    response = await servicer.UpdateTaskStatus(
        taskgraph_pb2.UpdateTaskStatusRequest(
            task_id=created.node.task_id,
            status=common_pb2.TASK_STATUS_IN_PROGRESS,
            reason="agent picked it up",
        ),
        context,
    )

    assert response.node.status == common_pb2.TASK_STATUS_IN_PROGRESS

    refetched = await servicer.GetTaskNode(
        taskgraph_pb2.GetTaskNodeRequest(task_id=created.node.task_id), context
    )
    assert refetched.node.status == common_pb2.TASK_STATUS_IN_PROGRESS


async def test_update_task_status_not_found() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.UpdateTaskStatus(
            taskgraph_pb2.UpdateTaskStatusRequest(
                task_id="missing",
                status=common_pb2.TASK_STATUS_DONE,
                reason="n/a",
            ),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


async def test_list_ready_task_nodes_respects_dependencies() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    upstream = await servicer.CreateTaskNode(make_create_request(title="upstream"), context)
    downstream = await servicer.CreateTaskNode(
        make_create_request(title="downstream", depends_on_task_ids=[upstream.node.task_id]),
        context,
    )

    ready = await servicer.ListReadyTaskNodes(
        taskgraph_pb2.ListReadyTaskNodesRequest(tenant_id=TENANT_ID), context
    )
    ready_ids = {node.task_id for node in ready.nodes}
    assert ready_ids == {upstream.node.task_id}

    await repository.update_status(upstream.node.task_id, TaskStatus.DONE, "shipped")

    ready = await servicer.ListReadyTaskNodes(
        taskgraph_pb2.ListReadyTaskNodesRequest(tenant_id=TENANT_ID), context
    )
    ready_ids = {node.task_id for node in ready.nodes}
    assert ready_ids == {downstream.node.task_id}


async def test_validate_ownership_reports_violations() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    created = await servicer.CreateTaskNode(
        make_create_request(path_globs=["taskgraph/app/*.py"]), context
    )

    response = await servicer.ValidateOwnership(
        taskgraph_pb2.ValidateOwnershipRequest(
            task_id=created.node.task_id,
            changed_paths=[
                "taskgraph/app/graph.py",
                "taskgraph/app/nested/other.py",
            ],
        ),
        context,
    )

    assert response.within_boundary is False
    assert list(response.violating_paths) == ["taskgraph/app/nested/other.py"]


async def test_validate_ownership_not_found() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.ValidateOwnership(
            taskgraph_pb2.ValidateOwnershipRequest(task_id="missing", changed_paths=[]),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND
