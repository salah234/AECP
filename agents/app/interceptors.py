"""Caller allow-list enforcement for the AgentPoolService gRPC server.

Coarse, server-level authorization: only callers whose identity is in the
allow-list may invoke any RPC on this server. This is an interim,
metadata-based placeholder (mirrors taskgraph/app/interceptors.py and
state/app/interceptors.py) pending platform/aecp_platform/identity.AllowList
and peer_identity(), which will derive the caller's identity from the
verified mTLS peer certificate rather than caller-supplied metadata. That
work is a Tier 3 security boundary change owned by /platform, not by this
service.
"""

from __future__ import annotations

import grpc
from grpc_reflection.v1alpha import reflection

# gRPC Server Reflection is registered on the same server (see
# grpc_server.build_server) and, like every other service, would
# otherwise be caught by this interceptor too -- but reflection calls
# (e.g. `grpcurl list`) carry no caller-id metadata, so with no
# exemption *reflection itself* gets PERMISSION_DENIED before a caller
# ever reaches an AgentPoolService method. Reflection only exposes API
# shape (service/method/message schema), not tenant data, so leaving it
# unauthenticated is the standard tradeoff for keeping introspection
# tooling usable.
#
# We exempt both the v1alpha service we actually register
# (reflection.SERVICE_NAME) *and* the newer stable v1 name, even though
# we don't register a v1 handler at all: modern reflection clients
# (grpcurl >=1.9, grpc-go) probe the stable v1 service first and only
# fall back to v1alpha on an UNIMPLEMENTED response. Without this second
# exemption, our interceptor would itself answer that v1 probe with
# PERMISSION_DENIED (since it intercepts every path, registered or not)
# instead of letting it fall through to grpc's own natural UNIMPLEMENTED
# -- which suppresses the client's fallback to v1alpha entirely.
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
