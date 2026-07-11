"""gRPC servicer implementation for aecp.coordinator.v1.CoordinatorService.

Thin wiring layer: translates gRPC requests into calls against Scheduler,
AssignmentEngine, and TradeoffResolver. No coordination logic lives here.
"""

from __future__ import annotations


class CoordinatorServicer:
    """Implements the generated CoordinatorServiceServicer base class
    (see proto/coordinator/v1/coordinator.proto).
    """

    def __init__(self, scheduler, assignment_engine, tradeoff_resolver) -> None:
        raise NotImplementedError

    async def Schedule(self, request, context):
        raise NotImplementedError

    async def Escalate(self, request, context):
        raise NotImplementedError

    async def ReportBlocker(self, request, context):
        raise NotImplementedError


def build_server(servicer: CoordinatorServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
