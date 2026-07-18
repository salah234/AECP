"""gRPC servicer implementation for aecp.taskgraph.v1.TaskGraphService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import grpc
import grpc.aio
from aecp_platform.dbtenant import TenantID, bind_tenant
from grpc_reflection.v1alpha import reflection

from app.common.v1 import common_pb2
from app.graph import CycleDetectedError, DanglingDependencyError
from app.interceptors import AllowListInterceptor
from app.schema import DefinitionOfDone, OwnershipBoundary, RiskTier, TaskNode, TaskStatus
from app.taskgraph.v1 import taskgraph_pb2, taskgraph_pb2_grpc

_RISK_TIER_TO_PROTO = {
    RiskTier.MECHANICAL: common_pb2.RISK_TIER_MECHANICAL,
    RiskTier.LOCAL: common_pb2.RISK_TIER_LOCAL,
    RiskTier.STRUCTURAL: common_pb2.RISK_TIER_STRUCTURAL,
    RiskTier.ARCHITECTURAL: common_pb2.RISK_TIER_ARCHITECTURAL,
}
_RISK_TIER_FROM_PROTO = {value: key for key, value in _RISK_TIER_TO_PROTO.items()}

_TASK_STATUS_TO_PROTO = {
    TaskStatus.PENDING: common_pb2.TASK_STATUS_PENDING,
    TaskStatus.BLOCKED: common_pb2.TASK_STATUS_BLOCKED,
    TaskStatus.ASSIGNED: common_pb2.TASK_STATUS_ASSIGNED,
    TaskStatus.IN_PROGRESS: common_pb2.TASK_STATUS_IN_PROGRESS,
    TaskStatus.IN_REVIEW: common_pb2.TASK_STATUS_IN_REVIEW,
    TaskStatus.ESCALATED: common_pb2.TASK_STATUS_ESCALATED,
    TaskStatus.DONE: common_pb2.TASK_STATUS_DONE,
    TaskStatus.ABANDONED: common_pb2.TASK_STATUS_ABANDONED,
}
_TASK_STATUS_FROM_PROTO = {value: key for key, value in _TASK_STATUS_TO_PROTO.items()}


def _node_to_proto(node: TaskNode) -> taskgraph_pb2.TaskNode:
    proto_node = taskgraph_pb2.TaskNode(
        task_id=node.task_id,
        tenant_id=node.tenant_id,
        title=node.title,
        description=node.description,
        risk_tier=_RISK_TIER_TO_PROTO[node.risk_tier],
        status=_TASK_STATUS_TO_PROTO[node.status],
        ownership=common_pb2.OwnershipBoundary(
            path_globs=node.ownership.path_globs,
            forbidden_globs=node.ownership.forbidden_globs,
        ),
        depends_on_task_ids=node.depends_on_task_ids,
        blocks_task_ids=node.blocks_task_ids,
        definition_of_done=taskgraph_pb2.DefinitionOfDone(
            required_checks=node.definition_of_done.required_checks,
            acceptance_criteria=node.definition_of_done.acceptance_criteria,
            requires_human_review_gate=node.definition_of_done.requires_human_review_gate,
        ),
        assigned_agent_id=node.assigned_agent_id or "",
    )
    proto_node.created_at.FromDatetime(node.created_at)
    proto_node.updated_at.FromDatetime(node.updated_at)
    return proto_node


class TaskGraphServicer:
    """Implements the generated TaskGraphServiceServicer base class
    (see proto/taskgraph/v1/taskgraph.proto).
    """

    def __init__(self, graph, ownership_module, repository) -> None:
        self.graph = graph
        self.ownership_module = ownership_module
        self.repository = repository

    async def CreateTaskNode(self, request, context):
        proto_node = request.node

        if not proto_node.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        if not proto_node.title:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "title is required")

        risk_tier = _RISK_TIER_FROM_PROTO.get(proto_node.risk_tier)
        if risk_tier is None:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "risk_tier must be explicitly set; it is the primary lever for "
                "human-in-the-loop cost control and has no safe default.",
            )

        status = _TASK_STATUS_FROM_PROTO.get(proto_node.status, TaskStatus.PENDING)
        now = datetime.now(timezone.utc)

        # TODO(tenancy): tenant_id is taken from the client-supplied request
        # field, not a verified session/service identity, pending Gateway-side
        # tenant resolution. TenantScopedPool still fails closed if unbound,
        # but does not yet protect against a caller lying about tenant_id.
        bind_tenant(TenantID(proto_node.tenant_id))

        node = TaskNode(
            task_id=proto_node.task_id or str(uuid4()),
            tenant_id=proto_node.tenant_id,
            title=proto_node.title,
            description=proto_node.description,
            risk_tier=risk_tier,
            status=status,
            ownership=OwnershipBoundary(
                path_globs=list(proto_node.ownership.path_globs),
                forbidden_globs=list(proto_node.ownership.forbidden_globs),
            ),
            depends_on_task_ids=list(proto_node.depends_on_task_ids),
            blocks_task_ids=list(proto_node.blocks_task_ids),
            definition_of_done=DefinitionOfDone(
                required_checks=list(proto_node.definition_of_done.required_checks),
                acceptance_criteria=list(proto_node.definition_of_done.acceptance_criteria),
                requires_human_review_gate=proto_node.definition_of_done.requires_human_review_gate,
            ),
            assigned_agent_id=proto_node.assigned_agent_id or None,
            created_at=now,
            updated_at=now,
        )

        try:
            node = await self.graph.add_node(node)
        except DanglingDependencyError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except CycleDetectedError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        return taskgraph_pb2.CreateTaskNodeResponse(node=_node_to_proto(node))

    async def GetTaskNode(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        bind_tenant(TenantID(request.tenant_id))
        node = await self.repository.get(request.task_id)
        if node is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Task '{request.task_id}' not found."
            )

        return taskgraph_pb2.GetTaskNodeResponse(node=_node_to_proto(node))

    async def UpdateTaskStatus(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        bind_tenant(TenantID(request.tenant_id))
        status = _TASK_STATUS_FROM_PROTO.get(request.status)
        if status is None:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "status must be specified")

        try:
            node = await self.repository.update_status(request.task_id, status, request.reason)
        except KeyError as exc:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        return taskgraph_pb2.UpdateTaskStatusResponse(node=_node_to_proto(node))

    async def ListReadyTaskNodes(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        bind_tenant(TenantID(request.tenant_id))
        nodes = await self.graph.ready_nodes(request.tenant_id)
        return taskgraph_pb2.ListReadyTaskNodesResponse(
            nodes=[_node_to_proto(node) for node in nodes]
        )

    async def ValidateOwnership(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        bind_tenant(TenantID(request.tenant_id))
        node = await self.repository.get(request.task_id)
        if node is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Task '{request.task_id}' not found."
            )

        violations = self.ownership_module.violating_paths(
            list(request.changed_paths), node.ownership
        )
        return taskgraph_pb2.ValidateOwnershipResponse(
            within_boundary=not violations,
            violating_paths=violations,
        )


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
    servicer: TaskGraphServicer,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
    allow_list,
    port: int = 50052,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    server = grpc.aio.server(interceptors=[AllowListInterceptor(allow_list)])

    taskgraph_pb2_grpc.add_TaskGraphServiceServicer_to_server(servicer, server)

    service_names = (
        taskgraph_pb2.DESCRIPTOR.services_by_name["TaskGraphService"].full_name,
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
