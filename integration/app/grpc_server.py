"""gRPC servicer implementation for aecp.integration.v1.IntegrationService."""

from __future__ import annotations


class IntegrationServicer:
    """Implements the generated IntegrationServiceServicer base class
    (see proto/integration/v1/integration.proto).
    """

    def __init__(self, conflict_detector, merge_policy_resolver, semantic_differ) -> None:
        raise NotImplementedError

    async def DetectConflicts(self, request, context):
        raise NotImplementedError

    async def ResolveMergePolicy(self, request, context):
        raise NotImplementedError

    async def SemanticDiff(self, request, context):
        raise NotImplementedError


def build_server(servicer: IntegrationServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    raise NotImplementedError
