"""REST surface for human-in-the-loop escalation review.

This is the primary EM-facing surface: pending Tier 2/3 approvals,
open conflicts requiring a human decision, and drift reports. Every
decision made here is Tier 2+ and must be written to the audit trail via
observability.audit.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/escalations", tags=["escalations"])


@router.get("")
async def list_pending_escalations():
    raise NotImplementedError


@router.post("/{task_id}/approve")
async def approve_escalation(task_id: str):
    raise NotImplementedError


@router.post("/{task_id}/reject")
async def reject_escalation(task_id: str):
    raise NotImplementedError


@router.get("/conflicts")
async def list_pending_conflicts():
    raise NotImplementedError


@router.get("/drift")
async def list_open_drift_reports():
    raise NotImplementedError
