"""gRPC servicer implementation for aecp.agents.v1.AgentPoolService."""

from __future__ import annotations


class AgentPoolServicer:
    """Implements the generated AgentPoolServiceServicer base class
    (see proto/agents/v1/agents.proto).
    """

    def __init__(self, lifecycle_manager, hydrator, handoff_coordinator) -> None:
        raise NotImplementedError

    async def SpawnSession(self, request, context):
        raise NotImplementedError

    async def HydrateContext(self, request, context):
        raise NotImplementedError

    async def HandoffSession(self, request, context):
        raise NotImplementedError

    async def TerminateSession(self, request, context):
        raise NotImplementedError


def build_server(servicer: AgentPoolServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
