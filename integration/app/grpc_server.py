"""gRPC servicer implementation for aecp.integration.v1.IntegrationService."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import grpc
import grpc.aio
from aecp_platform.tracing_grpc import TracingServerInterceptor
from grpc_reflection.v1alpha import reflection

from app.conflict import ConflictKind, ConflictReport
from app.integration.v1 import integration_pb2, integration_pb2_grpc
from app.interceptors import AllowListInterceptor
from app.merge_policy import MergePolicyDecision

_KIND_TO_PROTO = {
    ConflictKind.TEXTUAL: integration_pb2.CONFLICT_KIND_TEXTUAL,
    ConflictKind.SEMANTIC: integration_pb2.CONFLICT_KIND_SEMANTIC,
    ConflictKind.OWNERSHIP: integration_pb2.CONFLICT_KIND_OWNERSHIP,
}


def _report_to_proto(report: ConflictReport) -> integration_pb2.ConflictReport:
    proto_report = integration_pb2.ConflictReport(
        report_id=report.report_id,
        tenant_id=report.tenant_id,
        kind=_KIND_TO_PROTO[report.kind],
        task_ids=report.task_ids,
        description=report.description,
        auto_resolvable=report.auto_resolvable,
    )
    proto_report.detected_at.FromDatetime(report.detected_at)
    return proto_report


def _decision_to_proto(decision: MergePolicyDecision) -> integration_pb2.MergePolicyDecision:
    return integration_pb2.MergePolicyDecision(
        report_id=decision.report_id,
        auto_merge=decision.auto_merge,
        requires_human=decision.requires_human,
        rationale=decision.rationale,
    )


class IntegrationServicer:
    """Implements the generated IntegrationServiceServicer base class
    (see proto/integration/v1/integration.proto).

    ResolveMergePolicy's request only carries report_id + risk_tier, not
    a full ConflictReport, but MergePolicyResolver.resolve() needs the
    whole report (kind, auto_resolvable, ...) to look up a policy. There
    is no persistence layer for ConflictReports anywhere in this repo
    (no repository.py, no migration) and building one is out of scope
    here, so this servicer keeps an in-memory cache of every report it
    has produced via DetectConflicts, keyed by report_id, and
    ResolveMergePolicy reads from it.

    MVP limitation, documented per this codebase's existing pattern (see
    platform/aecp_platform/storage/client.py's local-filesystem note):
    this cache is single-replica only and is lost on restart. A real
    fix is a Postgres-backed ConflictReport repository (mirroring
    taskgraph/app/repository.py's TenantScopedPool usage) — future work,
    not attempted here.
    """

    def __init__(self, conflict_detector, merge_policy_resolver, semantic_differ) -> None:
        self.conflict_detector = conflict_detector
        self.merge_policy_resolver = merge_policy_resolver
        self.semantic_differ = semantic_differ
        self._reports_by_id: dict[str, ConflictReport] = {}

    async def DetectConflicts(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        reports = await self.conflict_detector.detect(
            request.tenant_id, list(request.candidate_task_ids)
        )

        for report in reports:
            self._reports_by_id[report.report_id] = report

        return integration_pb2.DetectConflictsResponse(
            reports=[_report_to_proto(report) for report in reports]
        )

    async def ResolveMergePolicy(self, request, context):
        if not request.report_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "report_id is required")

        report = self._reports_by_id.get(request.report_id)
        if report is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"ConflictReport '{request.report_id}' not found. Reports are "
                "only cached in-memory by DetectConflicts for the lifetime of "
                "this process (see IntegrationServicer's docstring).",
            )

        decision = self.merge_policy_resolver.resolve(report, request.risk_tier)
        return integration_pb2.ResolveMergePolicyResponse(decision=_decision_to_proto(decision))

    async def SemanticDiff(self, request, context):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id is required")

        result = await self.semantic_differ.compare(
            request.tenant_id, request.task_id_a, request.task_id_b
        )
        return integration_pb2.SemanticDiffResponse(
            jointly_coherent=result.jointly_coherent,
            explanation=result.explanation,
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
    servicer: IntegrationServicer,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
    allow_list,
    port: int = 50055,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    server = grpc.aio.server(
        interceptors=[TracingServerInterceptor(), AllowListInterceptor(allow_list)]
    )

    integration_pb2_grpc.add_IntegrationServiceServicer_to_server(servicer, server)

    service_names = (
        integration_pb2.DESCRIPTOR.services_by_name["IntegrationService"].full_name,
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
