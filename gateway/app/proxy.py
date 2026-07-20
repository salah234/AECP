"""REST-to-gRPC translation for internal service calls.

Every router in app/routers/ calls through here rather than constructing
gRPC stubs directly, so mTLS client config, caller identity, and tenant
metadata attachment happen in exactly one place. There is deliberately no
agents() accessor: gateway has no network edge to Agent Pool (see
deploy/k8s/networkpolicy/gateway-edges.yaml and config.Settings, which
also has no agents_addr) — routes that would need one return 501 instead.
"""

from __future__ import annotations

import grpc

from app import tenancy
from app.channels import build_client_channel, caller_metadata
from app.coordinator.v1 import coordinator_pb2_grpc
from app.integration.v1 import integration_pb2_grpc
from app.observability.v1 import observability_pb2_grpc
from app.state.v1 import state_pb2_grpc
from app.taskgraph.v1 import taskgraph_pb2_grpc

CALLER_ID = "gateway"


class InternalServiceClients:
    """Holds one mTLS-authenticated gRPC channel per internal service."""

    def __init__(self, settings) -> None:
        def channel(addr: str) -> grpc.aio.Channel:
            return build_client_channel(
                addr,
                mtls_cert_file=settings.mtls_cert_file,
                mtls_key_file=settings.mtls_key_file,
                mtls_ca_file=settings.mtls_ca_file,
            )

        self._coordinator = coordinator_pb2_grpc.CoordinatorServiceStub(
            channel(settings.coordinator_addr)
        )
        self._taskgraph = taskgraph_pb2_grpc.TaskGraphServiceStub(
            channel(settings.taskgraph_addr)
        )
        self._state = state_pb2_grpc.StateServiceStub(channel(settings.state_addr))
        self._integration = integration_pb2_grpc.IntegrationServiceStub(
            channel(settings.integration_addr)
        )
        self._observability = observability_pb2_grpc.AuditServiceStub(
            channel(settings.observability_addr)
        )

    def coordinator(self):
        return self._coordinator

    def taskgraph(self):
        return self._taskgraph

    def state(self):
        return self._state

    def integration(self):
        return self._integration

    def observability(self):
        return self._observability

    @staticmethod
    def metadata(tenant_id: str) -> list[tuple[str, str]]:
        """Build the gRPC call metadata every outbound call must carry:
        gateway's own caller identity plus the server-derived tenant
        context (never a client-supplied one — see tenancy.py).
        """
        return tenancy.attach_tenant_metadata(list(caller_metadata(CALLER_ID)), tenant_id)
