"""Tenant-scoped persistence for task nodes, backed by Postgres.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically; this module must never open
its own unscoped connection.
"""

from __future__ import annotations

from collections import defaultdict

from .schema import OwnershipBoundary, TaskNode, TaskStatus


def _node_from_row(row, depends_on_task_ids: list[str]) -> TaskNode:
    """Assemble a TaskNode from a raw task_nodes row plus its dependencies.

    `SELECT *` on task_nodes returns flat ownership_path_globs /
    ownership_forbidden_globs columns, not the nested `ownership` object
    TaskNode expects, and dependencies live in a separate table entirely
    -- both have to be assembled here rather than passed straight through.
    UUID columns also come back as uuid.UUID objects, not str, so the id
    fields need explicit stringification too.
    """
    data = dict(row)
    data["task_id"] = str(data["task_id"])
    data["tenant_id"] = str(data["tenant_id"])
    if data.get("assigned_agent_id") is not None:
        data["assigned_agent_id"] = str(data["assigned_agent_id"])
    data["ownership"] = OwnershipBoundary(
        path_globs=data.pop("ownership_path_globs"),
        forbidden_globs=data.pop("ownership_forbidden_globs"),
    )
    data["depends_on_task_ids"] = depends_on_task_ids
    return TaskNode(**data)


def _group_dependencies(dependency_rows) -> dict[str, list[str]]:
    """Group (task_id, depends_on_task_id) rows into task_id -> deps."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in dependency_rows:
        grouped[str(row["task_id"])].append(str(row["depends_on_task_id"]))
    return grouped


class TaskNodeRepository:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def create(self, node: TaskNode) -> TaskNode:
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO task_nodes (
                    task_id,
                    tenant_id,
                    title,
                    description,
                    risk_tier,
                    status,
                    ownership_path_globs,
                    ownership_forbidden_globs,
                    definition_of_done,
                    assigned_agent_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12
                )
                """,
                node.task_id,
                node.tenant_id,
                node.title,
                node.description,
                node.risk_tier,
                node.status,
                node.ownership.path_globs,
                node.ownership.forbidden_globs,
                node.definition_of_done.model_dump(mode="json"),
                node.assigned_agent_id,
                node.created_at,
                node.updated_at,
            )

            for dependency_id in node.depends_on_task_ids:
                await conn.execute(
                    """
                    INSERT INTO task_dependencies (
                        task_id,
                        depends_on_task_id,
                        tenant_id
                    )
                    VALUES ($1,$2,$3)
                    """,
                    node.task_id,
                    dependency_id,
                    node.tenant_id,
                )

        return node

    async def get(self, task_id: str) -> TaskNode | None:
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM task_nodes
                WHERE task_id = $1
                """,
                task_id,
            )

            if row is None:
                return None

            dependencies = await conn.fetch(
                """
                SELECT depends_on_task_id
                FROM task_dependencies
                WHERE task_id = $1
                """,
                task_id,
            )

        depends_on_task_ids = [
            str(dep["depends_on_task_id"])
            for dep in dependencies
        ]

        return _node_from_row(row, depends_on_task_ids)

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        reason: str,
    ) -> TaskNode:

        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                UPDATE task_nodes
                SET status = $2,
                    updated_at = NOW()
                WHERE task_id = $1
                RETURNING *
                """,
                task_id,
                status,
            )

            if row is None:
                raise KeyError(f"Task '{task_id}' not found.")

            dependencies = await conn.fetch(
                """
                SELECT depends_on_task_id
                FROM task_dependencies
                WHERE task_id = $1
                """,
                task_id,
            )

        depends_on_task_ids = [
            str(dep["depends_on_task_id"])
            for dep in dependencies
        ]

        return _node_from_row(row, depends_on_task_ids)

    async def list_by_tenant(
        self,
        tenant_id: str,
    ) -> list[TaskNode]:

        async with self.pool.transaction() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM task_nodes
                WHERE tenant_id = $1
                ORDER BY created_at
                """,
                tenant_id,
            )

            dependency_rows = await conn.fetch(
                """
                SELECT task_id, depends_on_task_id
                FROM task_dependencies
                WHERE tenant_id = $1
                """,
                tenant_id,
            )

        dependencies_by_task = _group_dependencies(dependency_rows)

        return [
            _node_from_row(row, dependencies_by_task[str(row["task_id"])])
            for row in rows
        ]

    async def list_ready(
        self,
        tenant_id: str,
    ) -> list[TaskNode]:

        async with self.pool.transaction() as conn:
            rows = await conn.fetch(
                """
                SELECT t.*
                FROM task_nodes t
                WHERE t.tenant_id = $1
                  AND t.status = 'pending'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM task_dependencies d
                      JOIN task_nodes dep
                        ON dep.task_id = d.depends_on_task_id
                      WHERE d.task_id = t.task_id
                        AND dep.status != 'done'
                  )
                ORDER BY t.created_at
                """,
                tenant_id,
            )

            dependency_rows = await conn.fetch(
                """
                SELECT task_id, depends_on_task_id
                FROM task_dependencies
                WHERE tenant_id = $1
                """,
                tenant_id,
            )

        dependencies_by_task = _group_dependencies(dependency_rows)

        return [
            _node_from_row(row, dependencies_by_task[str(row["task_id"])])
            for row in rows
        ]

    async def list_dependents(
        self,
        task_id: str,
    ) -> list[TaskNode]:

        async with self.pool.transaction() as conn:
            rows = await conn.fetch(
                """
                SELECT t.*
                FROM task_nodes t
                JOIN task_dependencies d
                  ON t.task_id = d.task_id
                WHERE d.depends_on_task_id = $1
                ORDER BY t.created_at
                """,
                task_id,
            )

            if not rows:
                return []

            dependency_rows = await conn.fetch(
                """
                SELECT task_id, depends_on_task_id
                FROM task_dependencies
                WHERE task_id = ANY($1::uuid[])
                """,
                [row["task_id"] for row in rows],
            )

        dependencies_by_task = _group_dependencies(dependency_rows)

        return [
            _node_from_row(row, dependencies_by_task[str(row["task_id"])])
            for row in rows
        ]

    async def list_dependencies(
        self,
        task_id: str,
    ) -> list[str]:

        async with self.pool.transaction() as conn:
            rows = await conn.fetch(
                """
                SELECT depends_on_task_id
                FROM task_dependencies
                WHERE task_id = $1
                """,
                task_id,
            )

        return [
            str(row["depends_on_task_id"])
            for row in rows
        ]

    async def delete(
        self,
        task_id: str,
    ) -> None:

        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                DELETE FROM task_nodes
                WHERE task_id = $1
                """,
                task_id,
            )