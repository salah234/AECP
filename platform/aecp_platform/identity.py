"""Service-to-service authentication.

Every internal gRPC edge is mutually authenticated with mTLS. Each service
is issued a workload certificate whose URI SAN encodes a SPIFFE-style
identity: spiffe://aecp/<environment>/<service>. Internal calls never rely
on a static shared secret or API key.

Each server declares the exact set of caller identities allowed to reach
it; the interceptor rejects everything else before a handler runs. Agent
workers are never included in each other's allow-lists, so one agent
cannot reach another directly regardless of application-level bugs.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass

import grpc

from aecp_platform.errors import UnauthenticatedError

SPIFFE_PREFIX = "spiffe://"

# gRPC's own reflection service carries no caller identity (introspection
# tools like grpcurl don't hold a workload cert) and exposes only API
# shape, not tenant data, so it is exempt from allow-list enforcement —
# the same tradeoff every service's interim AllowListInterceptor already
# makes (see agents/app/interceptors.py).
_REFLECTION_EXEMPT_PREFIXES = (
    "/grpc.reflection.v1alpha.ServerReflection/",
    "/grpc.reflection.v1.ServerReflection/",
)


class ServiceID(str):
    """A SPIFFE-style workload identity, e.g. 'spiffe://aecp/prod/coordinator'."""

    def service_name(self) -> str:
        """Return the trailing service segment of the identity URI."""
        path = self.removeprefix(SPIFFE_PREFIX)
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            raise ValueError(f"Malformed SPIFFE identity: {self!r}")
        return segments[-1]


@dataclass
class MTLSConfig:
    """Certificate material for one service identity."""

    self_id: ServiceID
    cert_file: str
    key_file: str
    ca_file: str

    def server_ssl_context(self) -> ssl.SSLContext:
        """Build an ssl.SSLContext that requires and verifies a client
        certificate on every connection (mutual TLS, fail closed).
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        context.load_verify_locations(cafile=self.ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    def client_ssl_context(self) -> ssl.SSLContext:
        """Build an ssl.SSLContext for originating mTLS connections to
        other AECP services.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        context.load_verify_locations(cafile=self.ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        # SPIFFE identities are compared against the URI SAN by
        # peer_identity(), not against a DNS hostname, so hostname
        # checking is deliberately disabled here in favor of that
        # explicit, application-level check.
        context.check_hostname = False
        return context


def peer_identity(grpc_context) -> ServiceID:
    """Extract the verified SPIFFE-style identity of the caller from the
    peer's leaf certificate URI SAN.

    Raises UnauthenticatedError if the connection is not mTLS or the
    certificate carries no recognizable identity.
    """
    auth_context = grpc_context.auth_context()

    transport = auth_context.get("transport_security_type")
    if not transport or transport[0] != b"ssl":
        raise UnauthenticatedError("Connection is not authenticated via mTLS")

    sans = auth_context.get("x509_subject_alternative_name", [])
    for entry in sans:
        value = entry.decode("utf-8") if isinstance(entry, bytes) else entry
        if value.startswith(SPIFFE_PREFIX):
            return ServiceID(value)

    raise UnauthenticatedError(
        "Peer certificate carries no spiffe:// URI SAN identity"
    )


class AllowList:
    """Per-server authorization: only callers whose verified identity is
    in the set may invoke any RPC on this server.

    Coarse (server-level, not per-RPC) by design — fine-grained
    authorization (e.g. "this task belongs to this agent") is layered on
    top by each service.
    """

    def __init__(self, *allowed: str) -> None:
        # Accepts either a full SPIFFE URI (ServiceID) or a bare service
        # name — every service's ALLOWED_CALLERS setting today stores
        # bare, comma-separated names (e.g. "agents,taskgraph"), so
        # requiring callers to wrap each one in a fake ServiceID just to
        # have it unwrapped back out would be circular busywork.
        self._allowed = frozenset(
            ServiceID(identity).service_name() if identity.startswith(SPIFFE_PREFIX) else identity
            for identity in allowed
        )

    def __contains__(self, service_name: str) -> bool:
        return service_name in self._allowed

    def grpc_interceptor(self) -> grpc.aio.ServerInterceptor:
        """Return a grpc.aio.ServerInterceptor enforcing this allow-list."""
        return _AllowListInterceptor(self)


class _AllowListInterceptor(grpc.aio.ServerInterceptor):
    """Verifies the caller's mTLS peer identity against an AllowList.

    Falls back to the interim, metadata-based `caller-id` scheme (see
    agents/app/interceptors.py) when the channel carries no verified
    peer identity — e.g. local dev/CI running without real certificates,
    where every other service in this mesh already relies on that
    fallback. This is a documented, intentional weakening for
    non-mTLS deployments, not a silent one: see
    security/THREAT_MODEL.md's "Open items" on AllowList/mTLS rollout.
    """

    def __init__(self, allow_list: AllowList) -> None:
        self._allow_list = allow_list

    async def intercept_service(self, continuation, handler_call_details):
        if handler_call_details.method.startswith(_REFLECTION_EXEMPT_PREFIXES):
            return await continuation(handler_call_details)

        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        original = handler.unary_unary
        allow_list = self._allow_list

        async def _wrapped(request, context):
            try:
                caller = peer_identity(context)
                caller_name = caller.service_name()
            except UnauthenticatedError:
                metadata = dict(context.invocation_metadata() or ())
                caller_name = metadata.get("caller-id")

            if caller_name not in allow_list:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "Caller not allowed"
                )
                return None

            return await original(request, context)

        return grpc.unary_unary_rpc_method_handler(
            _wrapped,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
