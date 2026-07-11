"""REST surface over TaskGraphService, scoped to the caller's tenant."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
async def list_ready_tasks():
    raise NotImplementedError


@router.get("/{task_id}")
async def get_task(task_id: str):
    raise NotImplementedError


@router.post("")
async def create_task():
    raise NotImplementedError


@router.post("/{task_id}/status")
async def update_task_status(task_id: str):
    raise NotImplementedError
