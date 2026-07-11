"""gRPC servicer implementation for aecp.taskgraph.v1.TaskGraphService."""

from __future__ import annotations


class TaskGraphServicer:
    """Implements the generated TaskGraphServiceServicer base class
    (see proto/taskgraph/v1/taskgraph.proto).
    """

    def __init__(self, graph, ownership_module, repository) -> None:
        raise NotImplementedError

    async def CreateTaskNode(self, request, context):
        raise NotImplementedError

    async def GetTaskNode(self, request, context):
        raise NotImplementedError

    async def UpdateTaskStatus(self, request, context):
        raise NotImplementedError

    async def ListReadyTaskNodes(self, request, context):
        raise NotImplementedError

    async def ValidateOwnership(self, request, context):
        raise NotImplementedError


def build_server(servicer: TaskGraphServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
