"""gRPC servicer implementation for aecp.state.v1.StateService."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import grpc
import grpc.aio
from grpc_reflection.v1alpha import reflection

from app.common.v1 import common_pb2
from app.decision_log import DecisionLogEntry
from app.drift import DriftReport
from app.state.v1 import state_pb2, state_pb2_grpc
from app.interceptors import AllowListInterceptor


@dataclass(frozen=True)
class MTLSConfig:
    certificate_chain: bytes
    private_key: bytes
    ca_certificate: bytes

    @classmethod
    def from_files(
        cls,
        *,
        cert_file: str,
        key_file: str,
        ca_file: str,
    ) -> "MTLSConfig":
        return cls(
            certificate_chain=Path(cert_file).read_bytes(),
            private_key=Path(key_file).read_bytes(),
            ca_certificate=Path(ca_file).read_bytes(),
        )


class StateServicer:
    """Implements the generated StateServiceServicer base class
    (see proto/state/v1/state.proto).
    """

    def __init__(self, decision_log, ownership_map, contract_registry, drift_detector) -> None:
        self.decision_log = decision_log
        self.ownership_map = ownership_map
        self.contract_registry = contract_registry
        self.drift_detector = drift_detector

    async def RecordDecision(self, request, context):
        request_entry = request.entry
        entry = DecisionLogEntry(
            entry_id=request_entry.entry_id,
            tenant_id=request_entry.tenant_id,
            task_id=request_entry.task_id,
            summary=request_entry.summary,
            rationale=request_entry.rationale,
            decided_by_kind=common_pb2.Actor.Kind.Name(
                request_entry.decided_by.kind,
            ),
            decided_by_id=request_entry.decided_by.id,
            decided_at=request_entry.decided_at.ToDatetime(),
        )
        await self.decision_log.record(entry)

        proto_entry = state_pb2.DecisionLogEntry(
            entry_id=entry.entry_id,
            tenant_id=entry.tenant_id,
            task_id=entry.task_id,
            summary=entry.summary,
            rationale=entry.rationale,
            decided_by=request_entry.decided_by,
        )
        proto_entry.decided_at.FromDatetime(entry.decided_at)

        return state_pb2.RecordDecisionResponse(
            entry=proto_entry
        )
        
    async def GetOwnership(self, request, context):
        ownership_record = await self.ownership_map.get(
            request.tenant_id,
            request.module_path
        )
        if ownership_record is None:
            await context.abort(grpc.StatusCode.NOT_FOUND,
                                "Ownership not found")
        
        proto_record = state_pb2.OwnershipRecord(
            tenant_id=ownership_record.tenant_id,
            module_path=ownership_record.module_path,
            last_task_id=ownership_record.last_task_id,
            last_agent_id=ownership_record.last_agent_id,
        )
        proto_record.last_touched_at.FromDatetime(ownership_record.last_touched_at)

        return state_pb2.GetOwnershipResponse(record=proto_record)


    async def GetInterfaceContract(self, request, context):
        interface_contract = await self.contract_registry.get(
            request.contract_id
        )
        if interface_contract is None:
            await context.abort(grpc.StatusCode.NOT_FOUND,
                                "Interface Contract not found")
        
        return state_pb2.GetInterfaceContractResponse(
            contract=state_pb2.InterfaceContract(
                contract_id=interface_contract.contract_id,
                tenant_id=interface_contract.tenant_id,
                name=interface_contract.name,
                schema=interface_contract.schema,
                version=interface_contract.version,
                frozen=interface_contract.frozen

            )
        )
        



    async def ReportDrift(self, request, context):
        request_report = request.report
        drift = DriftReport(
            report_id=request_report.report_id or str(uuid4()),
            tenant_id=request_report.tenant_id,
            contract_id=request_report.contract_id,
            description=request_report.description,
            resolved=request_report.resolved,
        )
        await self.drift_detector.report(drift)
        proto_drift = state_pb2.DriftReport(
            report_id=drift.report_id,
            tenant_id=drift.tenant_id,
            contract_id=drift.contract_id,
            description=drift.description,
            resolved=drift.resolved
        )
        return state_pb2.ReportDriftResponse(
            report=proto_drift
        )


def build_server(
    servicer: StateServicer,
    *,
    mtls_cert_file: str,
    mtls_key_file: str,
    mtls_ca_file: str,
    allow_list: list[str] | tuple[str, ...],
    port: int = 50051,
):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
 

    server = grpc.aio.server(
        interceptors=[
            AllowListInterceptor(allow_list)
        ]
    )

    state_pb2_grpc.add_StateServiceServicer_to_server(
        servicer,
        server,
    )
    SERVICE_NAMES = (
    state_pb2.DESCRIPTOR.services_by_name["StateService"].full_name,
    reflection.SERVICE_NAME,
    )

    reflection.enable_server_reflection(
        SERVICE_NAMES,
        server,
    )
    if mtls_cert_file and mtls_ca_file and mtls_key_file:
        mtls_config = MTLSConfig.from_files(
        cert_file=mtls_cert_file,
        key_file=mtls_key_file,
        ca_file=mtls_ca_file,
        )

        credentials = grpc.ssl_server_credentials(
            [
                (
                    mtls_config.private_key,
                    mtls_config.certificate_chain,
                ),
            ],
            root_certificates=mtls_config.ca_certificate,
            require_client_auth=True,
        )

        server.add_secure_port(
            f"[::]:{port}",
            credentials,
        )
    else:
        server.add_insecure_port(
            f"[::]:{port}",
        )

    return server
