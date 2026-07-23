"""REST surface over the State Layer's decision log and interface
contracts, scoped to the caller's tenant. Read-only: decisions are
recorded by services, never edited by humans through this API.
"""

from __future__ import annotations

import grpc
from fastapi import APIRouter, Depends

from app.deps import RequestContext, get_clients, get_request_context
from app.errors import grpc_error_to_http
from app.schemas import decision_log_entry_to_dict, interface_contract_to_dict
from app.state.v1 import state_pb2

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("")
async def list_decisions(
    task_id: str | None = None,
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        response = await clients.state().ListDecisions(
            state_pb2.ListDecisionsRequest(tenant_id=ctx.tenant_id, task_id=task_id or ""),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return [decision_log_entry_to_dict(entry) for entry in response.entries]


@router.get("/contracts/{contract_id}")
async def get_interface_contract(
    contract_id: str,
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        response = await clients.state().GetInterfaceContract(
            state_pb2.GetInterfaceContractRequest(contract_id=contract_id),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return interface_contract_to_dict(response.contract)
