"""Thin gRPC client wrapper around aecp.state.v1.StateService.

Kept intentionally minimal: typed methods for exactly the calls
Coordinator needs today (record_decision, used by tradeoff.py to log
escalation/blocker decisions to the institutional memory layer) plus
get_ownership/get_interface_contract for future scheduling use, mirroring
agents/app/state_client.py's own scope decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import grpc

from app.channels import caller_metadata
from app.common.v1 import common_pb2
from app.state.v1 import state_pb2, state_pb2_grpc


class StateClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "coordinator") -> None:
        self._stub = state_pb2_grpc.StateServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

    async def record_decision(
        self,
        *,
        tenant_id: str,
        task_id: str,
        summary: str,
        rationale: str,
        decided_by_kind: "common_pb2.Actor.Kind",
        decided_by_id: str,
    ) -> state_pb2.DecisionLogEntry:
        entry = state_pb2.DecisionLogEntry(
            entry_id=str(uuid4()),
            tenant_id=tenant_id,
            task_id=task_id,
            summary=summary,
            rationale=rationale,
            decided_by=common_pb2.Actor(kind=decided_by_kind, id=decided_by_id),
        )
        entry.decided_at.FromDatetime(datetime.now(timezone.utc))

        response = await self._stub.RecordDecision(
            state_pb2.RecordDecisionRequest(entry=entry),
            metadata=self._metadata,
        )
        return response.entry

    async def get_ownership(
        self, tenant_id: str, module_path: str
    ) -> state_pb2.OwnershipRecord | None:
        try:
            response = await self._stub.GetOwnership(
                state_pb2.GetOwnershipRequest(
                    tenant_id=tenant_id, module_path=module_path
                ),
                metadata=self._metadata,
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return response.record

    async def get_interface_contract(
        self, contract_id: str
    ) -> state_pb2.InterfaceContract | None:
        try:
            response = await self._stub.GetInterfaceContract(
                state_pb2.GetInterfaceContractRequest(contract_id=contract_id),
                metadata=self._metadata,
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return response.contract
