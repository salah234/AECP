"""Tenant-scoped persistence for task nodes, backed by Postgres.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically; this module must never open
its own unscoped connection.
"""

from __future__ import annotations

from .schema import TaskNode, TaskStatus


class TaskNodeRepository:
    def __init__(self, pool) -> None:
        raise NotImplementedError

    async def create(self, node: TaskNode) -> TaskNode:
        raise NotImplementedError

    async def get(self, task_id: str) -> TaskNode | None:
        raise NotImplementedError

    async def update_status(self, task_id: str, status: TaskStatus, reason: str) -> TaskNode:
        raise NotImplementedError

    async def list_ready(self, tenant_id: str) -> list[TaskNode]:
        raise NotImplementedError

    async def list_dependents(self, task_id: str) -> list[TaskNode]:
        raise NotImplementedError
