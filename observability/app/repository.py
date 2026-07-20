"""Tenant-scoped persistence for the append-only audit trail.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically. audit_events has no
UPDATE/DELETE grants planned for the application role (append-only is
meant to be enforced at the database role level via Terraform, not yet
done) — this repository must never issue UPDATE/DELETE against the table,
only INSERT/SELECT, so append-only holds even before that DB-level
enforcement lands.
"""

from __future__ import annotations

from datetime import datetime

from app.audit import AuditEvent


def _event_from_row(row) -> AuditEvent:
    """asyncpg decodes Postgres UUID columns as uuid.UUID objects, not
    str — AuditEvent.event_id/tenant_id need explicit stringification
    before they can be assigned to a proto string field (which raises a
    bare TypeError on a non-str/bytes value). Same pattern already
    established in taskgraph/app/repository.py's _node_from_row.
    """
    data = dict(row)
    data["event_id"] = str(data["event_id"])
    data["tenant_id"] = str(data["tenant_id"])
    return AuditEvent(**data)


class AuditRepository:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def insert_event(self, event: AuditEvent) -> None:
        async with self.pool.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    tenant_id,
                    actor_kind,
                    actor_id,
                    action,
                    resource,
                    security_relevant,
                    occurred_at
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                event.event_id,
                event.tenant_id,
                event.actor_kind,
                event.actor_id,
                event.action,
                event.resource,
                event.security_relevant,
                event.occurred_at,
            )

    async def query_events(
        self,
        tenant_id: str,
        since: datetime,
        security_relevant_only: bool,
    ) -> list[AuditEvent]:
        query = """
            SELECT *
            FROM audit_events
            WHERE tenant_id = $1
            AND occurred_at >= $2
        """
        if security_relevant_only:
            query += " AND security_relevant"
        query += " ORDER BY occurred_at DESC"

        async with self.pool.transaction() as conn:
            rows = await conn.fetch(query, tenant_id, since)

        return [_event_from_row(row) for row in rows]
