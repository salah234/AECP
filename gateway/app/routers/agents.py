"""REST surface over AgentPoolService, scoped to the caller's tenant.

Read-mostly: humans observe agent session status here. Session
spawn/terminate remains a Coordinator-driven action, not something the
dashboard triggers directly except via an explicit human override action
(which itself must be Tier 2+, audited).

Every route below is a 501: gateway has no network edge to Agent Pool at
all (deploy/k8s/networkpolicy/gateway-edges.yaml's egress list omits it,
and config.Settings/proxy.InternalServiceClients have no agents_addr/
agents() client to match). AgentPoolService's own proto also has no
"list sessions for a tenant" RPC — only single-session lifecycle calls.
Per the gateway architecture plan's scope decision, closing this gap
means adding Coordinator-mediated RPCs (Coordinator already has a real
edge to Agent Pool) rather than opening a new gateway->agents network
path, which would undercut CLAUDE.md's "no agent-to-agent, everything
routes through the Coordinator" invariant. That's follow-on work against
/coordinator, not this router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_request_context

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_NO_AGENT_POOL_EDGE = (
    501,
    "Gateway has no network path or RPC to Agent Pool; this requires a "
    "Coordinator-mediated RPC that doesn't exist yet.",
)


@router.get("", dependencies=[Depends(get_request_context)])
async def list_sessions():
    status, detail = _NO_AGENT_POOL_EDGE
    raise HTTPException(status_code=status, detail=detail)


@router.get("/{session_id}", dependencies=[Depends(get_request_context)])
async def get_session(session_id: str):
    status, detail = _NO_AGENT_POOL_EDGE
    raise HTTPException(status_code=status, detail=detail)


@router.post("/{session_id}/terminate", dependencies=[Depends(get_request_context)])
async def terminate_session(session_id: str):
    """Human override to terminate a running agent session. Must be
    audited via observability.audit as security_relevant.
    """
    status, detail = _NO_AGENT_POOL_EDGE
    raise HTTPException(status_code=status, detail=detail)
