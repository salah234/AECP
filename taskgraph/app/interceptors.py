"""Caller allow-list enforcement for the TaskGraphService gRPC server.

Coarse, server-level authorization: only callers whose identity is in the
allow-list may invoke any RPC on this server. This is an interim,
metadata-based placeholder (mirrors state/app/interceptors.py and
agents/app/interceptors.py) pending platform/aecp_platform/identity.AllowList
and peer_identity(), which will derive the caller's identity from the
verified mTLS peer certificate rather than caller-supplied metadata. That
work is a Tier 3 security boundary change owned by /platform, not by this
service.
"""

from __future__ import annotations

import grpc
from grpc_reflection.v1alpha import reflection

# See agents/app/interceptors.py's docstring for the full rationale: gRPC
# Server Reflection (grpcurl list/describe) carries no caller-id metadata,
# so without this exemption reflection itself gets PERMISSION_DENIED
# before any real caller ever reaches a TaskGraphService method. Exempt
# both the v1alpha service actually registered and the stable v1 name
# modern clients probe first.
_EXEMPT_SERVICE_PREFIXES = (
    f"/{reflection.SERVICE_NAME}/",
    "/grpc.reflection.v1.ServerReflection/",
)


class AllowListInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, allow_list):
        self.allow_list = allow_list

    async def intercept_service(self, continuation, handler_call_details):
        if handler_call_details.method.startswith(_EXEMPT_SERVICE_PREFIXES):
            return await continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata or ())
        caller = metadata.get("caller-id")

        if caller not in self.allow_list:
            return grpc.unary_unary_rpc_method_handler(self._unauthorized)

        return await continuation(handler_call_details)

    async def _unauthorized(self, request, context):
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED,
            "Caller not allowed",
        )
