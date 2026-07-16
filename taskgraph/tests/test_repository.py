"""Tests for TaskNodeRepository's row <-> TaskNode mapping.

Uses a scripted fake connection/pool that mimics the *shape* and *types*
of real asyncpg output -- flat ownership_path_globs/ownership_forbidden_globs
columns, separate task_dependencies rows, a jsonb column already decoded to
a dict by the pool's codec, and uuid.UUID objects (not str) for UUID
columns -- unlike tests/fakes.py's FakeTaskNodeRepository, which stores and
returns TaskNode objects directly and so never touches this row-mapping
code, or its type mismatches, at all.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.repository import TaskNodeRepository
from app.schema import OwnershipBoundary, TaskStatus

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _uuid(name: str) -> uuid.UUID:
    """Deterministic UUID for a short human-readable test id."""
    return uuid.uuid5(uuid.NAMESPACE_OID, name)


class _QueuedConnection:
    """Returns pre-scripted fetchrow/fetch results in call order and
    records every execute() call.
    """

    def __init__(self, fetchrow_results=(), fetch_results=()):
        self._fetchrow_results = list(fetchrow_results)
        self._fetch_results = list(fetch_results)
        self.executed: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        return self._fetchrow_results.pop(0)

    async def fetch(self, query, *args):
        return self._fetch_results.pop(0)


class _FakeTenantScopedPool:
    """Mimics TenantScopedPool's public surface: only .transaction()."""

    def __init__(self, conn: _QueuedConnection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def transaction(self):
        yield self._conn


def make_row(*, task_id: str = "a", **overrides) -> dict:
    """A row shaped like a real asyncpg Record: UUID columns come back as
    uuid.UUID objects, jsonb columns as dicts (once the pool's codec is
    registered), timestamptz columns as datetimes.
    """
    now = datetime.now(timezone.utc)
    row = {
        "task_id": _uuid(task_id),
        "tenant_id": uuid.UUID(TENANT_ID),
        "title": "Build the thing",
        "description": "",
        "risk_tier": "local",
        "status": "pending",
        "ownership_path_globs": ["taskgraph/app/**"],
        "ownership_forbidden_globs": ["taskgraph/tests/**"],
        "definition_of_done": {
            "required_checks": ["pytest"],
            "acceptance_criteria": ["works"],
            "requires_human_review_gate": True,
        },
        "assigned_agent_id": None,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


async def test_get_assembles_nested_ownership_and_dependencies() -> None:
    conn = _QueuedConnection(
        fetchrow_results=[make_row(task_id="a")],
        fetch_results=[[{"depends_on_task_id": _uuid("b")}]],
    )
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    node = await repository.get(str(_uuid("a")))

    assert node is not None
    assert node.ownership == OwnershipBoundary(
        path_globs=["taskgraph/app/**"], forbidden_globs=["taskgraph/tests/**"]
    )
    assert node.depends_on_task_ids == [str(_uuid("b"))]
    assert node.definition_of_done.required_checks == ["pytest"]


async def test_get_converts_uuid_columns_to_str() -> None:
    conn = _QueuedConnection(fetchrow_results=[make_row(task_id="a")], fetch_results=[[]])
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    node = await repository.get(str(_uuid("a")))

    assert node is not None
    assert node.task_id == str(_uuid("a"))
    assert isinstance(node.task_id, str)
    assert node.tenant_id == TENANT_ID
    assert isinstance(node.tenant_id, str)


async def test_get_converts_assigned_agent_id_when_present() -> None:
    agent_id = _uuid("agent")
    conn = _QueuedConnection(
        fetchrow_results=[make_row(task_id="a", assigned_agent_id=agent_id)],
        fetch_results=[[]],
    )
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    node = await repository.get(str(_uuid("a")))

    assert node is not None
    assert node.assigned_agent_id == str(agent_id)


async def test_get_returns_none_without_querying_dependencies() -> None:
    conn = _QueuedConnection(fetchrow_results=[None], fetch_results=[])
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    assert await repository.get("missing") is None


async def test_create_passes_json_serializable_definition_of_done() -> None:
    from app.schema import DefinitionOfDone, RiskTier, TaskNode

    conn = _QueuedConnection()
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))
    now = datetime.now(timezone.utc)

    node = TaskNode(
        task_id=str(_uuid("a")),
        tenant_id=TENANT_ID,
        title="t",
        description="",
        risk_tier=RiskTier.LOCAL,
        status=TaskStatus.PENDING,
        ownership=OwnershipBoundary(path_globs=["taskgraph/app/**"]),
        definition_of_done=DefinitionOfDone(
            required_checks=["pytest"],
            acceptance_criteria=["works"],
            requires_human_review_gate=True,
        ),
        created_at=now,
        updated_at=now,
    )

    await repository.create(node)

    _query, args = conn.executed[0]
    definition_of_done_arg = args[8]  # 9th positional bind param
    assert isinstance(definition_of_done_arg, dict)
    assert definition_of_done_arg == {
        "required_checks": ["pytest"],
        "acceptance_criteria": ["works"],
        "requires_human_review_gate": True,
    }


async def test_list_by_tenant_attaches_each_task_own_dependencies() -> None:
    conn = _QueuedConnection(
        fetch_results=[
            [make_row(task_id="a"), make_row(task_id="b")],
            [{"task_id": _uuid("b"), "depends_on_task_id": _uuid("a")}],
        ]
    )
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    nodes = await repository.list_by_tenant(TENANT_ID)
    by_id = {node.task_id: node for node in nodes}

    assert by_id[str(_uuid("a"))].depends_on_task_ids == []
    assert by_id[str(_uuid("b"))].depends_on_task_ids == [str(_uuid("a"))]


async def test_list_dependents_short_circuits_when_no_dependents() -> None:
    conn = _QueuedConnection(fetch_results=[[]])
    repository = TaskNodeRepository(_FakeTenantScopedPool(conn))

    assert await repository.list_dependents("a") == []
