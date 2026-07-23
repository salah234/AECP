"""gRPC servicer implementation for aecp.agents.v1.AgentPoolService."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import grpc
import grpc.aio
from aecp_platform.tracing_grpc import TracingServerInterceptor
from grpc_reflection.v1alpha import reflection

from app.agents.v1 import agents_pb2, agents_pb2_grpc
from app.common.v1 import common_pb2
from app.interceptors import AllowListInterceptor


class AgentPoolServicer:
    """Implements the generated AgentPoolServiceServicer base class
    (see proto/agents/v1/agents.proto).
    """

    def __init__(
        self, lifecycle_manager, hydrator, handoff_coordinator, pool=None, executor=None
    ) -> None:
        self.lifecycle_manager = lifecycle_manager
        self.hydrator = hydrator
        self.handoff_coordinator = handoff_coordinator
        self.pool = pool
        self.executor = executor

    async def SpawnSession(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        if not request.task_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "task_id is required")

        if request.granted_risk_tier == common_pb2.RISK_TIER_UNSPECIFIED:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "granted_risk_tier must be explicitly set; it is the primary lever "
                "for human-in-the-loop cost control and has no safe default.",
            )

        if self.pool is not None:
            acquired = await self.pool.acquire_slot(request.tenant_id)
            if not acquired:
                await context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"Agent pool at capacity for tenant '{request.tenant_id}'",
                )

        try:
            session = await self.lifecycle_manager.spawn(
                tenant_id=request.tenant_id,
                task_id=request.task_id,
                granted_risk_tier=common_pb2.RiskTier.Name(request.granted_risk_tier),
                ownership_globs=list(request.ownership.path_globs),
                ownership_boundary=request.ownership.SerializeToString(),
                task_node_snapshot=bytes(request.task_node_snapshot),
            )
        except Exception:
            if self.pool is not None:
                await self.pool.release_slot(request.tenant_id)
            raise

        if self.executor is not None:
            handle = await self.lifecycle_manager.get_sandbox_handle(session.session_id)
            if handle is not None:
                # Deliberately not awaited: SpawnSession's RPC latency
                # must stay bounded by sandbox+identity provisioning
                # only, not an entire claude run (see executor.py).
                self.executor.spawn_background(session, handle.scratch_dir)

        return agents_pb2.SpawnSessionResponse(session=_session_to_proto(session))

    async def HydrateContext(self, request, context):
        if not request.session_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "session_id is required")

        try:
            bundle = await self.hydrator.hydrate(request.session_id)
        except LookupError as exc:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        proto_bundle = agents_pb2.ContextBundle(
            task_id=bundle.task_id,
            task_node=bundle.task_node,
            ownership_boundary=bundle.ownership_boundary,
            relevant_interface_contracts=bundle.relevant_interface_contracts,
            relevant_decision_log_entries=bundle.relevant_decision_log_entries,
        )

        return agents_pb2.HydrateContextResponse(
            context_bundle=proto_bundle.SerializeToString(),
        )

    async def HandoffSession(self, request, context):
        if not request.session_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "session_id is required")

        try:
            new_session = await self.handoff_coordinator.handoff(
                request.session_id, request.reason
            )
        except LookupError as exc:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        return agents_pb2.HandoffSessionResponse(
            new_session=_session_to_proto(new_session)
        )

    async def TerminateSession(self, request, context):
        if not request.session_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "session_id is required")

        # terminate_and_return atomically claims the session (see its
        # docstring in lifecycle.py): exactly one of two concurrent
        # TerminateSession calls for the same session_id gets it back, so
        # only one ever releases the pool slot below.
        session = await self.lifecycle_manager.terminate_and_return(
            request.session_id, request.reason
        )
        if session is None:
            return agents_pb2.TerminateSessionResponse(terminated=False)

        if self.pool is not None:
            await self.pool.release_slot(session.tenant_id)

        return agents_pb2.TerminateSessionResponse(terminated=True)

    async def ListSessions(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        sessions = await self.lifecycle_manager.list_active(request.tenant_id)
        return agents_pb2.ListSessionsResponse(
            sessions=[_session_to_proto(s) for s in sessions]
        )


def _session_to_proto(session) -> agents_pb2.AgentSession:
    proto_session = agents_pb2.AgentSession(
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        task_id=session.task_id,
        status=agents_pb2.AGENT_SESSION_STATUS_ACTIVE,
        granted_risk_tier=cast(
            common_pb2.RiskTier, common_pb2.RiskTier.Value(session.granted_risk_tier)
        ),
        ownership=common_pb2.OwnershipBoundary.FromString(session.ownership_boundary)
        if session.ownership_boundary
        else common_pb2.OwnershipBoundary(),
        task_node_snapshot=session.task_node_snapshot,
    )
    proto_session.spawned_at.FromDatetime(session.spawned_at)
    proto_session.expires_at.FromDatetime(session.expires_at)
    return proto_session


@dataclass(frozen=True)
class MTLSConfig:
    certificate_chain: bytes
    private_key: bytes
    ca_certificate: bytes

    @classmethod
    def from_files(cls, *, cert_file: str, key_file: str, ca_file: str) -> "MTLSConfig":
        return cls(
            certificate_chain=Path(cert_file).read_bytes(),
            private_key=Path(key_file).read_bytes(),
            ca_certificate=Path(ca_file).read_bytes(),
        )


def build_server(
    servicer: AgentPoolServicer,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
    allow_list,
    port: int = 50053,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    server = grpc.aio.server(
        interceptors=[TracingServerInterceptor(), AllowListInterceptor(allow_list)]
    )

    agents_pb2_grpc.add_AgentPoolServiceServicer_to_server(servicer, server)

    service_names = (
        agents_pb2.DESCRIPTOR.services_by_name["AgentPoolService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    if mtls_cert_file and mtls_key_file and mtls_ca_file:
        mtls_config = MTLSConfig.from_files(
            cert_file=mtls_cert_file,
            key_file=mtls_key_file,
            ca_file=mtls_ca_file,
        )

        credentials = grpc.ssl_server_credentials(
            [(mtls_config.private_key, mtls_config.certificate_chain)],
            root_certificates=mtls_config.ca_certificate,
            require_client_auth=True,
        )

        server.add_secure_port(f"[::]:{port}", credentials)
    else:
        server.add_insecure_port(f"[::]:{port}")

    return server
