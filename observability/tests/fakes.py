"""In-memory test doubles for observability components.

Used to exercise AuditServicer and AuditTrail end-to-end without a live
Postgres connection or mTLS server.
"""

from __future__ import annotations

from datetime import datetime

from app.audit import AuditEvent


class FakeAuditRepository:
    """Implements the subset of AuditRepository's async interface that
    AuditTrail depends on, backed by a plain list. Append-only by
    construction: there is no update/delete method to call.
    """

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def insert_event(self, event: AuditEvent) -> None:
        if any(existing.event_id == event.event_id for existing in self.events):
            raise ValueError(f"duplicate event_id: {event.event_id}")
        self.events.append(event)

    async def query_events(
        self,
        tenant_id: str,
        since: datetime,
        security_relevant_only: bool,
    ) -> list[AuditEvent]:
        matches = [
            event
            for event in self.events
            if event.tenant_id == tenant_id and event.occurred_at >= since
        ]
        if security_relevant_only:
            matches = [event for event in matches if event.security_relevant]

        return sorted(matches, key=lambda event: event.occurred_at, reverse=True)


class AbortedRPC(Exception):
    """Raised by FakeContext.abort to mimic grpc.aio's abort-terminates-the-RPC
    semantics, so tests can assert on the status code that would have been
    sent to the caller.
    """

    def __init__(self, code, details: str = "") -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    async def abort(self, code, details: str = "") -> None:
        raise AbortedRPC(code, details)
