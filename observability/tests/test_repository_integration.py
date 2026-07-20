"""Real-Postgres integration test for AuditRepository.

repository.py's SQL (INSERT/SELECT against audit_events, RLS-scoped via
TenantScopedPool) can only be meaningfully verified against a real
Postgres instance with observability/migrations/0001_audit_trail.sql
applied — a fake repository double (see tests/fakes.py, used by every
other test in this suite) cannot catch a wrong column name, a bad SQL
type cast, or an RLS policy that silently returns zero rows. This test
is opt-in (mirrors coordinator/tests/integration/test_e2e_docker_compose.py's
AECP_RUN_DOCKER_INTEGRATION_TESTS gating) so `pytest`/CI stays fast and
hermetic by default and never silently fails on a machine without
Postgres running.

Run it explicitly against a Postgres instance with the migration applied,
e.g.:

    docker run --rm -d --name aecp-obs-pg -p 5432:5432 \
        -e POSTGRES_USER=aecp -e POSTGRES_PASSWORD=aecp_dev_only \
        -e POSTGRES_DB=aecp postgres:16
    psql postgresql://aecp:aecp_dev_only@localhost:5432/aecp \
        -f observability/migrations/0001_audit_trail.sql
    AECP_RUN_POSTGRES_INTEGRATION_TESTS=1 \
        POSTGRES_DSN=postgresql://aecp:aecp_dev_only@localhost:5432/aecp \
        pytest observability/tests/test_repository_integration.py -q
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("AECP_RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="opt-in: set AECP_RUN_POSTGRES_INTEGRATION_TESTS=1 and point "
    "POSTGRES_DSN at a Postgres instance with "
    "observability/migrations/0001_audit_trail.sql applied first (see "
    "this file's module docstring)",
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
async def pool():
    import asyncpg

    dsn = os.environ["POSTGRES_DSN"]
    pool = await asyncpg.create_pool(dsn)
    try:
        yield pool
    finally:
        await pool.close()


async def test_insert_and_query_round_trip(pool) -> None:
    from aecp_platform.dbtenant import TenantID, TenantScopedPool, bind_tenant

    from app.audit import AuditEvent
    from app.repository import AuditRepository

    bind_tenant(TenantID(TENANT_ID))
    repository = AuditRepository(TenantScopedPool(pool))

    event = AuditEvent(
        event_id=str(uuid4()),
        tenant_id=TENANT_ID,
        actor_kind="human",
        actor_id="user-1",
        action="task.escalate",
        resource="task/123",
        security_relevant=True,
        occurred_at=datetime.now(timezone.utc),
    )

    await repository.insert_event(event)

    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    results = await repository.query_events(TENANT_ID, since, security_relevant_only=False)

    assert any(row.event_id == event.event_id for row in results)


async def test_insert_never_updates_an_existing_row(pool) -> None:
    """A duplicate event_id must raise (primary-key violation), never
    silently overwrite — see AuditTrail.record's docstring for why this
    is load-bearing for the append-only guarantee.
    """
    from aecp_platform.dbtenant import TenantID, TenantScopedPool, bind_tenant

    from app.audit import AuditEvent
    from app.repository import AuditRepository

    bind_tenant(TenantID(TENANT_ID))
    repository = AuditRepository(TenantScopedPool(pool))

    event_id = str(uuid4())
    event = AuditEvent(
        event_id=event_id,
        tenant_id=TENANT_ID,
        actor_kind="agent",
        actor_id="agent-1",
        action="task.viewed",
        resource="task/123",
        security_relevant=False,
        occurred_at=datetime.now(timezone.utc),
    )
    await repository.insert_event(event)

    with pytest.raises(Exception):  # noqa: B017 - asyncpg.UniqueViolationError
        await repository.insert_event(event)
