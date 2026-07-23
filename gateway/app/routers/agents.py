"""REST surface over AgentPoolService, scoped to the caller's tenant.

Read-mostly: humans observe agent session status here. Session
spawn/terminate remains a Coordinator-driven action, not something the
dashboard triggers directly except via an explicit human override action
(which itself must be Tier 2+, audited).

GET / (list) is real: it proxies through
CoordinatorService.ListAgentSessions, which itself proxies
AgentPoolService.ListSessions — Gateway still has no direct network edge
to Agent Pool (deploy/k8s/networkpolicy/gateway-edges.yaml's egress list
omits it) and never should, per CLAUDE.md's "no agent-to-agent,
everything routes through the Coordinator" invariant. Coordinator already
has a real edge to Agent Pool, so it mediates.

GET /{session_id} and POST /{session_id}/terminate stay 501: neither has
a backing RPC anywhere yet (AgentPoolService has no single-session getter,
and a human-triggered TerminateSession proxy needs its own Tier 2+
audit-wiring design), and neither has a dashboard consumer today — see
dashboard/lib/api-client.ts, which only calls listAgentSessions().
Building unused write surface ahead of an actual UI trigger is scope
creep; this is real, scoped follow-on work, not close by osmosis.
"""

from __future__ import annotations

import grpc
from fastapi import APIRouter, Depends, HTTPException

from app.coordinator.v1 import coordinator_pb2
from app.deps import RequestContext, get_clients, get_request_context
from app.errors import grpc_error_to_http
from app.schemas import agent_session_to_dict

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_NO_AGENT_POOL_RPC = (
    501,
    "AgentPoolService has no single-session lookup/terminate proxy RPC yet, "
    "and no dashboard route calls this endpoint today.",
)


@router.get("")
async def list_sessions(
    ctx: RequestContext = Depends(get_request_context),
    clients=Depends(get_clients),
):
    try:
        response = await clients.coordinator().ListAgentSessions(
            coordinator_pb2.ListAgentSessionsRequest(tenant_id=ctx.tenant_id),
            metadata=clients.metadata(ctx.tenant_id),
        )
    except grpc.aio.AioRpcError as exc:
        raise grpc_error_to_http(exc) from exc

    return [agent_session_to_dict(session) for session in response.sessions]


@router.get("/{session_id}", dependencies=[Depends(get_request_context)])
async def get_session(session_id: str):
    status, detail = _NO_AGENT_POOL_RPC
    raise HTTPException(status_code=status, detail=detail)


@router.post("/{session_id}/terminate", dependencies=[Depends(get_request_context)])
async def terminate_session(session_id: str):
    """Human override to terminate a running agent session. Must be
    audited via observability.audit as security_relevant.
    """
    status, detail = _NO_AGENT_POOL_RPC
    raise HTTPException(status_code=status, detail=detail)
