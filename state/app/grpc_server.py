"""gRPC servicer implementation for aecp.state.v1.StateService."""

from __future__ import annotations
import grpc.aio 
from state.app.decision_log import DecisionLogEntry
from state.app.drift import DriftReport
from app.state.v1 import state_pb2, state_pb2_grpc
from state.app.interceptors import AllowListInterceptor
from uuid import uuid4



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
        entry = DecisionLogEntry(
            entry_id=request.entry_id,
            tenant_id=request.tenant_id,
            task_id=request.task_id,
            summary=request.summary,
            rationale=request.rationale,
            decided_by_kind=request.decided_by_kind,
            decided_by_id=request.decided_by_id,
            decided_at=request.decided_at,
            supersedes_entry_id=request.supersedes_entry_id or None,
        )
        await self.decision_log.record(entry)

        proto_entry = state_pb2.DecisionLogEntry(
                entry_id=entry.entry_id,
                tenant_id=entry.tenant_id,
                task_id=entry.task_id,
                summary=entry.summary,
                rationale=entry.rationale,
                decided_by_kind=entry.decided_by_kind,
                decided_by_id=entry.decided_by_id,
                decided_at=entry.decided_at,
                supersedes_entry_id=entry.supersedes_entry_id or "",
        )

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
        
        return state_pb2.GetOwnershipResponse(
            record=state_pb2.OwnershipRecord(
                tenant_id=ownership_record.tenant_id,
                module_path=ownership_record.module_path,
                last_task_id=ownership_record.last_task_id,
                last_agent_id=ownership_record.last_agent_id,
                last_touched_at=ownership_record.last_touched_at.isoformat()

            )

        )


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
        drift = DriftReport(
            report_id=str(uuid4()),
            tenant_id=request.tenant_id,
            contract_id=request.contract_id,
            description=request.description,
            resolved=False
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


def build_server(servicer: StateServicer, mtls_config, allow_list):
    """Construct a grpc.aio.Server bound to the given servicer, with the
    mTLS server credentials and caller allow-list interceptor applied.
    """
    server = grpc.aio.server(
        interceptors=[
            AllowListInterceptor(allow_list) # RPC Interceptor since its impacting multiple layers/modules in an application - Middleware
        ]
    )

    state_pb2_grpc.add_StateServiceServicer_to_server(
        servicer,
        server,
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
        "[::]:50051",
        credentials,
    )

    return server
