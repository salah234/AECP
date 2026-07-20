"""REST surface over TaskGraphService, scoped to the caller's tenant."""

from __future__ import annotations

from uuid import uuid4

import grpc
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.common.v1 import common_pb2
from app.deps import RequestContext, get_clients, get_request_context
from app.errors import grpc_error_to_http
from app.schemas import risk_tier_from_str, task_node_to_dict, task_status_from_str
from app.taskgraph.v1 import taskgraph_pb2

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    risk_tier: str
    path_globs: list[str] = Field(default_factory=list)
    forbidden_globs: list[str] = Field(default_factory=list)
    depends_on_task_ids: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    requires_human_review_gate: bool = False


class UpdateTaskStatusRequest(BaseModel):
    status: str
    reason: str = ""


@router.get("")
async def list_ready_tasks(
    ctx: RequestContext = Depends(get_request_context), clients=Depends(get_clients)
):
    try:
        response = await clients.taskgraph().ListReadyTaskNodes(
            taskgraph_pb2.ListReadyTaskNodesRequest(tenant_id=ctx.tenant_id),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return [task_node_to_dict(node) for node in response.nodes]


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        response = await clients.taskgraph().GetTaskNode(
            taskgraph_pb2.GetTaskNodeRequest(task_id=task_id, tenant_id=ctx.tenant_id),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return task_node_to_dict(response.node)


@router.post("")
async def create_task(
    body: CreateTaskRequest,
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        risk_tier = risk_tier_from_str(body.risk_tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    node = taskgraph_pb2.TaskNode(
        task_id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        title=body.title,
        description=body.description,
        risk_tier=risk_tier,
        status=common_pb2.TASK_STATUS_PENDING,
        ownership=common_pb2.OwnershipBoundary(
            path_globs=body.path_globs, forbidden_globs=body.forbidden_globs
        ),
        depends_on_task_ids=body.depends_on_task_ids,
        definition_of_done=taskgraph_pb2.DefinitionOfDone(
            required_checks=body.required_checks,
            acceptance_criteria=body.acceptance_criteria,
            requires_human_review_gate=body.requires_human_review_gate,
        ),
    )

    try:
        response = await clients.taskgraph().CreateTaskNode(
            taskgraph_pb2.CreateTaskNodeRequest(node=node),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return task_node_to_dict(response.node)


@router.post("/{task_id}/status")
async def update_task_status(
    task_id: str,
    body: UpdateTaskStatusRequest,
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        status = task_status_from_str(body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        response = await clients.taskgraph().UpdateTaskStatus(
            taskgraph_pb2.UpdateTaskStatusRequest(
                task_id=task_id,
                tenant_id=ctx.tenant_id,
                status=status,
                reason=body.reason,
            ),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return task_node_to_dict(response.node)
