"""Thin gRPC client wrapper around aecp.taskgraph.v1.TaskGraphService.

Kept intentionally minimal: Integration only ever needs to look up a
single candidate task's TaskNode (its ownership boundary and definition
of done) to run conflict detection — it never schedules, creates, or
mutates task nodes, so this client exposes only get_task_node, mirroring
agents/app/state_client.py's "typed methods for exactly what this
service needs today" scoping decision rather than wrapping every
TaskGraphService RPC.
"""

from __future__ import annotations

import grpc

from app.channels import caller_metadata
from app.taskgraph.v1 import taskgraph_pb2, taskgraph_pb2_grpc


class TaskGraphClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "integration") -> None:
        self._stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

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
