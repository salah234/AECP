"""REST surface over the State Layer's decision log and interface
contracts, scoped to the caller's tenant. Read-only: decisions are
recorded by services, never edited by humans through this API.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.get("")
async def list_decisions(task_id: str | None = None):
    raise NotImplementedError


@router.get("/contracts/{contract_id}")
async def get_interface_contract(contract_id: str):
    raise NotImplementedError
