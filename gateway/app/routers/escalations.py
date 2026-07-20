"""REST surface for human-in-the-loop escalation review.

This is the primary EM-facing surface: pending Tier 2/3 approvals, open
conflicts requiring a human decision, and drift reports. Every decision
made here is Tier 2+ and must be written to the audit trail via
observability.audit.

Every route below is currently a 501: CoordinatorService.Escalate only
handles a *new* agent-initiated escalation request (it computes its own
approved/denied outcome from risk-tier policy — see
coordinator/app/tradeoff.py's _HUMAN_REQUIRED_TIERS) and offers no RPC for
a human to resolve a task already sitting in ESCALATED state.
coordinator/app/statemachine.py even names the two transitions this needs
(ESCALATED --approve_escalation--> IN_PROGRESS,
ESCALATED --deny_escalation--> BLOCKED) but no code path anywhere invokes
them. Wiring these buttons to Escalate() would silently ignore the
human's decision (a LOCAL-tier request auto-approves regardless of what a
"reject" click intended) — worse than a 501. Similarly, TaskGraphService/
StateService/IntegrationService have no RPC to list pending escalations,
conflicts, or drift reports today. See the gateway architecture plan's
scope decision: these are flagged, not faked, and are follow-on work
against /coordinator, /state, and /integration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_request_context

router = APIRouter(prefix="/api/v1/escalations", tags=["escalations"])

_NO_LIST_RPC = (
    501,
    "No RPC exists yet to list pending escalations for a tenant "
    "(TaskGraphService/StateService have no query for ESCALATED-status tasks).",
)
_NO_RESOLUTION_RPC = (
    501,
    "CoordinatorService.Escalate only handles new agent-initiated escalation "
    "requests; there is no RPC yet for a human to resolve a task already in "
    "ESCALATED state (see statemachine.py's unwired approve_escalation/"
    "deny_escalation transitions).",
)
_NO_CONFLICTS_RPC = (
    501,
    "IntegrationService has no RPC to list pending conflicts (only "
    "DetectConflicts, triggered on-demand with candidate task ids).",
)
_NO_DRIFT_RPC = (
    501,
    "StateService has no RPC to list open drift reports (only ReportDrift, a write).",
)


@router.get("", dependencies=[Depends(get_request_context)])
async def list_pending_escalations():
    status, detail = _NO_LIST_RPC
    raise HTTPException(status_code=status, detail=detail)


@router.post("/{task_id}/approve", dependencies=[Depends(get_request_context)])
async def approve_escalation(task_id: str):
    status, detail = _NO_RESOLUTION_RPC
    raise HTTPException(status_code=status, detail=detail)


@router.post("/{task_id}/reject", dependencies=[Depends(get_request_context)])
async def reject_escalation(task_id: str):
    status, detail = _NO_RESOLUTION_RPC
    raise HTTPException(status_code=status, detail=detail)


@router.get("/conflicts", dependencies=[Depends(get_request_context)])
async def list_pending_conflicts():
    status, detail = _NO_CONFLICTS_RPC
    raise HTTPException(status_code=status, detail=detail)


@router.get("/drift", dependencies=[Depends(get_request_context)])
async def list_open_drift_reports():
    status, detail = _NO_DRIFT_RPC
    raise HTTPException(status_code=status, detail=detail)
