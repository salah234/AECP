"""Thin gRPC client wrapper around aecp.state.v1.StateService.

Kept intentionally minimal, mirroring agents/app/state_client.py and
coordinator/app/state_client.py's own scoping decisions: typed methods
for exactly the calls Integration needs today. semantic_diff.py uses
get_ownership to enrich its heuristic with "who last touched this path"
context for two candidate tasks' overlapping ownership paths.
get_interface_contract is included for parity with the other clients and
for the day proto/state/v1/state.proto grows a query that can resolve a
contract from a path rather than only from a contract_id (see
semantic_diff.py's module docstring for the current gap) — Integration
has no way to discover a relevant contract_id from an ownership path
today, so it is not yet called from this service's own logic.
"""

from __future__ import annotations

import grpc

from app.channels import caller_metadata
from app.state.v1 import state_pb2, state_pb2_grpc


class StateClient:
    def __init__(self, channel: grpc.aio.Channel, caller_id: str = "integration") -> None:
        self._stub = state_pb2_grpc.StateServiceStub(channel)
        self._metadata = caller_metadata(caller_id)

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
