"""REST-to-gRPC translation for internal service calls.

Every router in app/routers/ calls through here rather than constructing
gRPC stubs directly, so mTLS client config, tenant metadata attachment,
and tracing propagation happen in exactly one place.
"""

from __future__ import annotations


class InternalServiceClients:
    """Holds one mTLS-authenticated gRPC channel per internal service."""

    def __init__(self, settings) -> None:
        raise NotImplementedError

    def coordinator(self):
        raise NotImplementedError

    def taskgraph(self):
        raise NotImplementedError

    def state(self):
        raise NotImplementedError

    def integration(self):
        raise NotImplementedError

    def observability(self):
        raise NotImplementedError
