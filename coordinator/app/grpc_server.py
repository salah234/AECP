"""gRPC servicer implementation for aecp.coordinator.v1.CoordinatorService.

Thin wiring layer: translates gRPC requests into calls against Scheduler,
AssignmentEngine, and TradeoffResolver. No coordination logic lives here.
"""

from __future__ import annotations

from pathlib import Path

import grpc
import grpc.aio
from grpc_reflection.v1alpha import reflection

from app.coordinator.v1 import coordinator_pb2, coordinator_pb2_grpc


class CoordinatorServicer:
    """Implements the generated CoordinatorServiceServicer base class
    (see proto/coordinator/v1/coordinator.proto).
    """

    def __init__(self, scheduler, assignment_engine, tradeoff_resolver) -> None:
        self.scheduler = scheduler
        self.assignment_engine = assignment_engine
        self.tradeoff_resolver = tradeoff_resolver

    async def Schedule(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        tick = await self.scheduler.plan_tick(request.tenant_id)
        decisions = await self.assignment_engine.assign(
            tick.parallelizable_task_ids, request.tenant_id
        )

        return coordinator_pb2.ScheduleResponse(
            decisions=[_decision_to_proto(decision) for decision in decisions]
        )

    async def Escalate(self, request, context):
        if not request.task_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "task_id is required")
        if not request.agent_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "agent_id is required")
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        try:
            decision = await self.tradeoff_resolver.escalate(
                task_id=request.task_id,
                tenant_id=request.tenant_id,
                agent_id=request.agent_id,
                reason=request.reason,
                requested_risk_tier=request.requested_risk_tier,
            )
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        return coordinator_pb2.EscalateResponse(
            approved=decision.approved,
            decided_by=decision.decided_by,
        )

    async def ReportBlocker(self, request, context):
        if not request.task_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "task_id is required")
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        try:
            await self.tradeoff_resolver.report_blocker(
                task_id=request.task_id,
                tenant_id=request.tenant_id,
                agent_id=request.agent_id,
                description=request.description,
            )
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        return coordinator_pb2.ReportBlockerResponse(acknowledged=True)


def _decision_to_proto(decision) -> coordinator_pb2.AssignmentDecision:
    return coordinator_pb2.AssignmentDecision(
        task_id=decision.task_id,
        agent_id=decision.agent_id,
        granted_risk_tier=decision.granted_risk_tier,
        rationale=decision.rationale,
    )


def build_server(
    servicer: CoordinatorServicer,
    mtls_config,
    allow_list,
    *,
    port: int = 50054,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.

    Unlike taskgraph/agents/state's build_server (which take raw cert
    file paths and a plain tuple of caller-id strings — the interim,
    metadata-based scheme), Coordinator takes real
    aecp_platform.identity.MTLSConfig/AllowList instances: it is the
    first service in the mesh built against the real (now implemented)
    platform primitives rather than each service's local placeholder.
    allow_list.grpc_interceptor() still falls back to the same
    metadata-based caller-id check when the channel isn't authenticated
    via mTLS, so local dev/CI without real certificates keeps working
    exactly like every other service (see aecp_platform.identity's
    _AllowListInterceptor).
    """
    server = grpc.aio.server(interceptors=[allow_list.grpc_interceptor()])

    coordinator_pb2_grpc.add_CoordinatorServiceServicer_to_server(servicer, server)

    service_names = (
        coordinator_pb2.DESCRIPTOR.services_by_name["CoordinatorService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    if mtls_config is not None:
        # grpc's own credential objects want raw PEM bytes, not a Python
        # ssl.SSLContext (aecp_platform.identity.MTLSConfig builds one of
        # those too, for any non-grpc listener that wants it, but grpc
        # itself never accepts it directly) — read the same files
        # MTLSConfig already carries so the two never diverge.
        credentials = grpc.ssl_server_credentials(
            [
                (
                    Path(mtls_config.key_file).read_bytes(),
                    Path(mtls_config.cert_file).read_bytes(),
                )
            ],
            root_certificates=Path(mtls_config.ca_file).read_bytes(),
            require_client_auth=True,
        )
        server.add_secure_port(f"[::]:{port}", credentials)
    else:
        server.add_insecure_port(f"[::]:{port}")

    return server
