"""Tenant-scoped persistence for decision log entries, ownership records,
interface contracts, and drift reports.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically. Large context artifacts
(hydration bundles, agent transcripts) are stored in object storage, not
Postgres — this repository only stores their URIs.
"""

from __future__ import annotations

from __future__ import annotations
from state.app.decision_log import DecisionLogEntry
from state.app.drift import ModuleState, DriftReport

class StateRepository:
    def __init__(self, pool, object_storage_client) -> None:
        self.pool = pool
        self.object_storage_client = object_storage_client


    async def insert_decision(self, entry) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO decision_log_entries (
                    tenant_id,
                    task_id,
                    decision,
                    created_at
                )
                VALUES ($1, $2, $3, $4)
                """,
                entry.tenant_id,
                entry.task_id,
                entry.decision,
                entry.created_at,
            )
    
    async def upsert_ownership(self, record) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ownership (
                    tenant_id,
                    agent_id,
                    resource_id
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (resource_id)
                DO UPDATE SET
                    agent_id = EXCLUDED.agent_id
                """,
                record.tenant_id,
                record.agent_id,
                record.resource_id,
            )


    async def get_contract(self, contract_id: str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM interface_contracts
                WHERE contract_id = $1
                ORDER BY version DESC
                LIMIT 1
                """,
                contract_id,
            )

            if row is None:
                return None

            return row


    async def get_contract_version(
        self,
        contract_id: str,
        version: int
    ):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM interface_contracts
                WHERE contract_id = $1
                AND version = $2
                """,
                contract_id,
                version,
            )

            if row is None:
                return None

            return row
        
    async def get_decisions_by_task(self, task_id: str):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM decision_log_entries
                WHERE task_id = $1
                ORDER BY decided_at ASC
                """,
                task_id
            )
            
            
            return [
                DecisionLogEntry(**dict(row))
                for row in rows
            ]
        
    async def get_decisions_for_module(
        self,
        tenant_id: str,
        module_path: str,
    ) -> list[DecisionLogEntry]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM decision_log_entries
                WHERE tenant_id = $1
                AND module_path = $2
                ORDER BY decided_at ASC
                """,
                tenant_id,
                module_path,
            )

        return [
            DecisionLogEntry(**dict(row))
            for row in rows
        ]



    async def save_contract(self, contract) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO interface_contracts (
                    contract_id,
                    tenant_id,
                    name,
                    schema,
                    version,
                    frozen
                )
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                contract.contract_id,
                contract.tenant_id,
                contract.name,
                contract.schema,
                contract.version,
                contract.frozen,
            )


    async def insert_drift_report(self, report: DriftReport) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO drift_reports (
                    report_id,
                    tenant_id,
                    contract_id,
                    description,
                    resolved
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                report.report_id,
                report.tenant_id,
                report.contract_id,
                report.description,
                report.resolved,
            )

    async def get_drift_report(
    self,
    report_id: str,
    ) -> DriftReport | None:

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM drift_reports
                WHERE report_id = $1
                """,
                report_id,
            )

        if row is None:
            return None

        return DriftReport(**dict(row))
    
    async def update_drift_report(
        self,
        report: DriftReport,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE drift_reports
                SET
                    description = $2,
                    resolved = $3
                WHERE report_id = $1
                """,
                report.report_id,
                report.description,
                report.resolved,
            )


    async def put_artifact(
        self,
        tenant_id: str,
        key: str,
        data: bytes
    ) -> str:
        uri = await self.object_storage_client.put(
            tenant_id=tenant_id,
            key=key,
            data=data,
        )

        return uri


    async def get_artifact(self, uri: str) -> bytes:
        return await self.object_storage_client.get(uri)
    
    async def get_module_state(
        self,
        tenant_id: str,
        module_path: str,
    ) -> ModuleState | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM module_states
                WHERE tenant_id = $1
                AND module_path = $2
                """,
                tenant_id,
                module_path,
            )

        if row is None:
            return None

        return ModuleState(**dict(row))
    
    async def save_module_state(
        self,
        state: ModuleState,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO module_states (
                    tenant_id,
                    module_path
                    contract_id, 
                    current_schema
                )
                VALUES ($1,$2,$3,$4)
                """,
                state.tenant_id,
                state.module_path,
                state.contract_id,
                state.current_schema
    )
        
    