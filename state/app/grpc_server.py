"""gRPC servicer implementation for aecp.state.v1.StateService."""

from __future__ import annotations


class StateServicer:
    """Implements the generated StateServiceServicer base class
    (see proto/state/v1/state.proto).
    """

    def __init__(self, decision_log, ownership_map, contract_registry, drift_detector) -> None:
        raise NotImplementedError

    async def RecordDecision(self, request, context):
        raise NotImplementedError

    async def GetOwnership(self, request, context):
        raise NotImplementedError

    async def GetInterfaceContract(self, request, context):
        raise NotImplementedError

    async def ReportDrift(self, request, context):
        raise NotImplementedError


def build_server(servicer: StateServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
