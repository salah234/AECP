"""Tenant-scoped persistence for decision log entries, ownership records,
interface contracts, and drift reports.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically. Large context artifacts
(hydration bundles, agent transcripts) are stored in object storage, not
Postgres — this repository only stores their URIs.
"""

from __future__ import annotations

from app.contracts import InterfaceContract
from app.decision_log import DecisionLogEntry
from app.drift import DriftReport, ModuleState
from app.ownership_map import OwnershipRecord


class StateRepository:
    def __init__(self, pool, object_storage_client) -> None:
        self.pool = pool
        self.object_storage_client = object_storage_client

    async def insert_decision(self, entry) -> None:
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO decision_log_entries (
                    entry_id,
                    tenant_id,
                    task_id,
                    summary,
                    rationale,
                    decided_by_kind,
                    decided_by_id,
                    decided_at,
                    supersedes_entry_id
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                """,
                entry.entry_id,
                entry.tenant_id,
                entry.task_id,
                entry.summary,
                entry.rationale,
                entry.decided_by_kind,
                entry.decided_by_id,
                entry.decided_at,
                entry.supersedes_entry_id,
            )

    async def upsert_ownership(self, record) -> None:
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO ownership_records (
                    tenant_id,
                    module_path,
                    last_task_id,
                    last_agent_id,
                    last_touched_at
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tenant_id, module_path)
                DO UPDATE SET
                    last_task_id = EXCLUDED.last_task_id,
                    last_agent_id = EXCLUDED.last_agent_id,
                    last_touched_at = EXCLUDED.last_touched_at
                """,
                record.tenant_id,
                record.module_path,
                record.last_task_id,
                record.last_agent_id,
                record.last_touched_at,
            )

    async def get_ownership(
        self,
        tenant_id: str,
        module_path: str,
    ) -> OwnershipRecord | None:
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT tenant_id, module_path, last_task_id, last_agent_id, last_touched_at
                FROM ownership_records
                WHERE tenant_id = $1
                AND module_path = $2
                """,
                tenant_id,
                module_path,
            )

        if row is None:
            return None

        return OwnershipRecord(**dict(row))

    async def get_contract(self, contract_id: str) -> InterfaceContract | None:
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT contract_id, tenant_id, name,
                       schema_definition AS schema, version, frozen
                FROM interface_contracts
                WHERE contract_id = $1
                ORDER BY version DESC
                LIMIT 1
                """,
                contract_id,
            )

        if row is None:
            return None

        return InterfaceContract(**dict(row))

    async def get_contract_version(
        self,
        contract_id: str,
        version: int,
    ) -> InterfaceContract | None:
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT contract_id, tenant_id, name,
                       schema_definition AS schema, version, frozen
                FROM interface_contracts
                WHERE contract_id = $1
                AND version = $2
                """,
                contract_id,
                version,
            )

        if row is None:
            return None

        return InterfaceContract(**dict(row))

    async def get_decisions_by_task(self, task_id: str) -> list[DecisionLogEntry]:
        async with self.pool.transaction() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM decision_log_entries
                WHERE task_id = $1
                ORDER BY decided_at ASC
                """,
                task_id,
            )

        return [DecisionLogEntry(**dict(row)) for row in rows]

    async def get_decisions_for_module(
        self,
        tenant_id: str,
        module_path: str,
    ) -> list[DecisionLogEntry]:
        """Return the decision history for whichever task last touched
        `module_path`.

        decision_log_entries has no module_path column of its own —
        decisions are recorded per task_id, not per module (see
        decision_log.py). This approximates "history for a module" via
        ownership_records.last_task_id (the task that most recently
        touched it), which is the only place module-to-task linkage is
        tracked today. This only ever returns the *current* last
        touch's history, not every task that ever touched the module —
        a real fix requires decision_log_entries (and
        RecordDecisionRequest on the wire) to carry module_path directly,
        which is a proto/schema change out of this fix's scope.
        """
        ownership_record = await self.get_ownership(tenant_id, module_path)
        if ownership_record is None:
            return []

        return await self.get_decisions_by_task(ownership_record.last_task_id)

    async def save_contract(self, contract) -> None:
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO interface_contracts (
                    contract_id,
                    tenant_id,
                    name,
                    schema_definition,
                    version,
                    frozen
                )
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (contract_id, version)
                DO UPDATE SET
                    frozen = EXCLUDED.frozen
                """,
                contract.contract_id,
                contract.tenant_id,
                contract.name,
                contract.schema,
                contract.version,
                contract.frozen,
            )

    async def insert_drift_report(self, report: DriftReport) -> None:
        async with self.pool.transaction() as conn:
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
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT report_id, tenant_id, contract_id, description, resolved
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
        async with self.pool.transaction() as conn:
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
        data: bytes,
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
        async with self.pool.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT tenant_id, module_path, contract_id,
                       schema_definition AS current_schema
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
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO module_states (
                    tenant_id,
                    module_path,
                    contract_id,
                    schema_definition
                )
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (tenant_id, module_path)
                DO UPDATE SET
                    contract_id = EXCLUDED.contract_id,
                    schema_definition = EXCLUDED.schema_definition
                """,
                state.tenant_id,
                state.module_path,
                state.contract_id,
                state.current_schema,
            )
