"""Unit tests for AuditTrail against the in-memory FakeAuditRepository
double (see tests/fakes.py) — no Postgres required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.audit import AuditEvent, AuditTrail

from .fakes import FakeAuditRepository

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def make_event(
    *,
    tenant_id: str = TENANT_A,
    actor_kind: str = "human",
    security_relevant: bool = False,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_kind=actor_kind,
        actor_id="user-1",
        action="task.escalate",
        resource="task/123",
        security_relevant=security_relevant,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )


async def test_record_persists_event_via_repository() -> None:
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)
    event = make_event()

    recorded = await trail.record(event)

    assert recorded is event
    assert repository.events == [event]


async def test_record_never_mutates_an_existing_row() -> None:
    """The repository only ever exposes insert_event (no update/upsert),
    so a duplicate event_id must surface as a real failure, not a silent
    overwrite.
    """
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)
    event = make_event()

    await trail.record(event)

    duplicate = AuditEvent(**{**event.__dict__, "action": "different.action"})
    with pytest.raises(ValueError):
        await trail.record(duplicate)

    assert repository.events == [event]


async def test_query_is_a_thin_passthrough_to_repository() -> None:
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)

    old_event = make_event(occurred_at=datetime.now(timezone.utc) - timedelta(days=2))
    new_event = make_event(occurred_at=datetime.now(timezone.utc))
    await trail.record(old_event)
    await trail.record(new_event)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    results = await trail.query(TENANT_A, since)

    assert results == [new_event]


async def test_query_filters_security_relevant_only() -> None:
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)

    routine = make_event(security_relevant=False)
    sensitive = make_event(security_relevant=True)
    await trail.record(routine)
    await trail.record(sensitive)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    results = await trail.query(TENANT_A, since, security_relevant_only=True)

    assert results == [sensitive]


async def test_query_is_scoped_to_tenant() -> None:
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)

    event_a = make_event(tenant_id=TENANT_A)
    event_b = make_event(tenant_id=TENANT_B)
    await trail.record(event_a)
    await trail.record(event_b)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    results = await trail.query(TENANT_A, since)

    assert results == [event_a]
