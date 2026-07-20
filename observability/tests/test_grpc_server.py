"""Servicer-level tests for AuditServicer against a real AuditTrail backed
by the in-memory FakeAuditRepository double (see tests/fakes.py) instead
of Postgres.
"""

from __future__ import annotations

import grpc
import pytest
from aecp_platform.dbtenant import current_tenant

from app.audit import AuditTrail
from app.common.v1 import common_pb2
from app.grpc_server import AuditServicer
from app.observability.v1 import observability_pb2

from .fakes import AbortedRPC, FakeAuditRepository, FakeContext

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def make_servicer() -> tuple[AuditServicer, FakeAuditRepository]:
    repository = FakeAuditRepository()
    trail = AuditTrail(repository)
    servicer = AuditServicer(audit_trail=trail)
    return servicer, repository


def make_record_request(
    *,
    tenant_id: str = TENANT_A,
    event_id: str = "",
    actor_kind=common_pb2.Actor.KIND_HUMAN,
    actor_id: str = "user-1",
    action: str = "task.escalate",
    resource: str = "task/123",
    security_relevant: bool = True,
) -> observability_pb2.RecordAuditEventRequest:
    return observability_pb2.RecordAuditEventRequest(
        event=common_pb2.AuditEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            actor=common_pb2.Actor(kind=actor_kind, id=actor_id),
            action=action,
            resource=resource,
            security_relevant=security_relevant,
        )
    )


async def test_record_audit_event_generates_event_id_when_missing() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    response = await servicer.RecordAuditEvent(make_record_request(), context)

    assert response.event_id
    assert repository.events[0].event_id == response.event_id


async def test_record_audit_event_preserves_supplied_event_id() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    response = await servicer.RecordAuditEvent(
        make_record_request(event_id="fixed-id-123"), context
    )

    assert response.event_id == "fixed-id-123"
    assert repository.events[0].event_id == "fixed-id-123"


async def test_record_audit_event_binds_tenant_before_persisting() -> None:
    """The tenant must be bound (via bind_tenant) before any repository
    call, mirroring state/app/grpc_server.py's RecordDecision pattern —
    this is what makes TenantScopedPool's RLS enforcement actually take
    effect against a real Postgres connection.
    """
    servicer, repository = make_servicer()
    context = FakeContext()

    seen_tenant: list[str] = []

    original_insert = repository.insert_event

    async def spy_insert(event):
        # By the time insert_event runs, the tenant context must already
        # be bound — that's the ordering RecordAuditEvent must guarantee.
        seen_tenant.append(current_tenant())
        return await original_insert(event)

    repository.insert_event = spy_insert  # type: ignore[method-assign]

    await servicer.RecordAuditEvent(make_record_request(tenant_id=TENANT_A), context)

    assert seen_tenant == [TENANT_A]


async def test_record_audit_event_converts_actor_kind_round_trip() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    await servicer.RecordAuditEvent(
        make_record_request(actor_kind=common_pb2.Actor.KIND_AGENT), context
    )

    assert repository.events[0].actor_kind == "agent"


async def test_record_audit_event_rejects_unspecified_actor_kind() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.RecordAuditEvent(
            make_record_request(actor_kind=common_pb2.Actor.KIND_UNSPECIFIED), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_record_audit_event_defaults_occurred_at_when_unset() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    await servicer.RecordAuditEvent(make_record_request(), context)

    assert repository.events[0].occurred_at is not None


async def test_query_audit_events_round_trips_actor_kind() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    await servicer.RecordAuditEvent(
        make_record_request(actor_kind=common_pb2.Actor.KIND_COORDINATOR), context
    )

    response = await servicer.QueryAuditEvents(
        observability_pb2.QueryAuditEventsRequest(tenant_id=TENANT_A),
        context,
    )

    assert len(response.events) == 1
    assert response.events[0].actor.kind == common_pb2.Actor.KIND_COORDINATOR


async def test_query_audit_events_requires_tenant_id() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.QueryAuditEvents(
            observability_pb2.QueryAuditEventsRequest(tenant_id=""), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_query_audit_events_is_scoped_to_tenant() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    await servicer.RecordAuditEvent(make_record_request(tenant_id=TENANT_A), context)
    await servicer.RecordAuditEvent(make_record_request(tenant_id=TENANT_B), context)

    response = await servicer.QueryAuditEvents(
        observability_pb2.QueryAuditEventsRequest(tenant_id=TENANT_A),
        context,
    )

    assert len(response.events) == 1
    assert response.events[0].tenant_id == TENANT_A


async def test_query_audit_events_filters_security_relevant_only() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    await servicer.RecordAuditEvent(
        make_record_request(security_relevant=True, action="auth.failed"), context
    )
    await servicer.RecordAuditEvent(
        make_record_request(security_relevant=False, action="task.viewed"), context
    )

    response = await servicer.QueryAuditEvents(
        observability_pb2.QueryAuditEventsRequest(
            tenant_id=TENANT_A, security_relevant_only=True
        ),
        context,
    )

    assert len(response.events) == 1
    assert response.events[0].action == "auth.failed"


async def test_query_audit_events_binds_tenant_before_querying() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    seen_tenant: list[str] = []
    original_query = repository.query_events

    async def spy_query(tenant_id, since, security_relevant_only):
        seen_tenant.append(current_tenant())
        return await original_query(tenant_id, since, security_relevant_only)

    repository.query_events = spy_query  # type: ignore[method-assign]

    await servicer.QueryAuditEvents(
        observability_pb2.QueryAuditEventsRequest(tenant_id=TENANT_B), context
    )

    assert seen_tenant == [TENANT_B]
