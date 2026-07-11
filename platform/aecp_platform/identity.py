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

from dataclasses import dataclass


class ServiceID(str):
    """A SPIFFE-style workload identity, e.g. 'spiffe://aecp/prod/coordinator'."""

    def service_name(self) -> str:
        """Return the trailing service segment of the identity URI."""
        raise NotImplementedError


@dataclass
class MTLSConfig:
    """Certificate material for one service identity."""

    self_id: ServiceID
    cert_file: str
    key_file: str
    ca_file: str

    def server_ssl_context(self):
        """Build an ssl.SSLContext that requires and verifies a client
        certificate on every connection (mutual TLS, fail closed).
        """
        raise NotImplementedError

    def client_ssl_context(self):
        """Build an ssl.SSLContext for originating mTLS connections to
        other AECP services.
        """
        raise NotImplementedError


def peer_identity(grpc_context) -> ServiceID:
    """Extract the verified SPIFFE-style identity of the caller from the
    peer's leaf certificate URI SAN.

    Raises UnauthenticatedError if the connection is not mTLS or the
    certificate carries no recognizable identity.
    """
    raise NotImplementedError


class AllowList:
    """Per-server authorization: only callers whose verified identity is
    in the set may invoke any RPC on this server.

    Coarse (server-level, not per-RPC) by design — fine-grained
    authorization (e.g. "this task belongs to this agent") is layered on
    top by each service.
    """

    def __init__(self, *allowed: ServiceID) -> None:
        raise NotImplementedError

    def grpc_interceptor(self):
        """Return a grpc.aio.ServerInterceptor enforcing this allow-list."""
        raise NotImplementedError
