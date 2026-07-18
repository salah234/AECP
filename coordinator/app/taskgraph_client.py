"""Thin gRPC client wrapper around aecp.taskgraph.v1.TaskGraphService.

Coordinator is the only service with a network edge to TaskGraph among
the agent-facing services (see docs/adr/0007-agent-pool-has-no-taskgraph-edge.md
— Agent Pool deliberately has none). Scheduler uses list_ready_task_nodes
to plan a tick; AssignmentEngine uses get_task_node to build the
task_node_snapshot bytes it forwards into SpawnSessionRequest, since
Agent Pool never parses the snapshot itself.
"""

from __future__ import annotations

import grpc

from app.channels import caller_metadata
from app.common.v1 import common_pb2
from app.taskgraph.v1 import taskgraph_pb2, taskgraph_pb2_grpc


class TaskGraphClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "coordinator") -> None:
        self._stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def list_ready_task_nodes(self, tenant_id: str) -> list[taskgraph_pb2.TaskNode]:
        response = await self._stub.ListReadyTaskNodes(
            taskgraph_pb2.ListReadyTaskNodesRequest(tenant_id=tenant_id),
            metadata=self._metadata,
        )
        return list(response.nodes)

    async def get_task_node(
        self, task_id: str, tenant_id: str
    ) -> taskgraph_pb2.TaskNode | None:
        try:
            response = await self._stub.GetTaskNode(
                taskgraph_pb2.GetTaskNodeRequest(task_id=task_id, tenant_id=tenant_id),
                metadata=self._metadata,
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return response.node

    async def update_task_status(
        self, task_id: str, tenant_id: str, status: "common_pb2.TaskStatus", reason: str
    ) -> taskgraph_pb2.TaskNode:
        response = await self._stub.UpdateTaskStatus(
            taskgraph_pb2.UpdateTaskStatusRequest(
                task_id=task_id, tenant_id=tenant_id, status=status, reason=reason
            ),
            metadata=self._metadata,
        )
        return response.node

    async def validate_ownership(
        self, task_id: str, tenant_id: str, changed_paths: list[str]
    ) -> taskgraph_pb2.ValidateOwnershipResponse:
        return await self._stub.ValidateOwnership(
            taskgraph_pb2.ValidateOwnershipRequest(
                task_id=task_id, tenant_id=tenant_id, changed_paths=changed_paths
            ),
            metadata=self._metadata,
        )
