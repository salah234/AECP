"""Escalation audit trail: an append-only, tamper-evident log of every
security-relevant and Tier-2+ event across AECP.

Every other service writes here (via AuditClient, not direct DB access)
whenever aecp_platform.errors.is_security_relevant is True, or whenever a
Tier 2/3 task changes state. Nothing is ever deleted or mutated; humans
reviewing agent activity read this log, not application logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AuditEvent:
    event_id: str
    tenant_id: str
    actor_kind: str
    actor_id: str
    action: str
    resource: str
    security_relevant: bool
    occurred_at: datetime


class AuditTrail:
    def __init__(self, repository) -> None:
        raise NotImplementedError

    async def record(self, event: AuditEvent) -> AuditEvent:
        """Append event. Must reject (not silently drop) any write that
        would require mutating or deleting an existing row.
        """
        raise NotImplementedError

    async def query(
        self, tenant_id: str, since: datetime, security_relevant_only: bool = False
    ) -> list[AuditEvent]:
        raise NotImplementedError
