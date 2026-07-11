"""REST surface over AgentPoolService, scoped to the caller's tenant.

Read-mostly: humans observe agent session status here. Session
spawn/terminate remains a Coordinator-driven action, not something the
dashboard triggers directly except via an explicit human override action
(which itself must be Tier 2+, audited).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("")
async def list_sessions():
    raise NotImplementedError


@router.get("/{session_id}")
async def get_session(session_id: str):
    raise NotImplementedError


@router.post("/{session_id}/terminate")
async def terminate_session(session_id: str):
    """Human override to terminate a running agent session. Must be
    audited via observability.audit as security_relevant.
    """
    raise NotImplementedError
