"""Tests for StateRepository's row <-> dataclass mapping.

Uses a scripted fake connection/pool that mimics the shape of real asyncpg
output, mirroring taskgraph/tests/test_repository.py's approach --
unlike tests/fakes.py's FakeStateRepository, which stores and returns
domain dataclasses directly and so never touches this row-mapping SQL (or
the schema_definition AS schema / current_schema column aliasing) at all.

put_artifact/get_artifact go through
aecp_platform.storage.ObjectStorageClient, not Postgres, so those are
exercised against tests.fakes.FakeObjectStorageClient (matching its
async put/get surface) instead of the fake Postgres connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.contracts import InterfaceContract
from app.decision_log import DecisionLogEntry
from app.drift import DriftReport, ModuleState
from app.ownership_map import OwnershipRecord
from app.repository import StateRepository

from .fakes import FakeObjectStorageClient

TENANT_ID = "11111111-1111-1111-1111-111111111111"


class _QueuedConnection:
    """Returns pre-scripted fetchrow/fetch results in call order and
    records every execute() call.
    """

    def __init__(self, fetchrow_results=(), fetch_results=()):
        self._fetchrow_results = list(fetchrow_results)
        self._fetch_results = list(fetch_results)
        self.executed: list[tuple[str, tuple]] = []
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._fetchrow_results.pop(0)

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch_results.pop(0)


class _FakeTenantScopedPool:
    """Mimics TenantScopedPool's public surface: only .transaction()."""

    def __init__(self, conn: _QueuedConnection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def transaction(self):
        yield self._conn


def make_repository(conn: _QueuedConnection, object_storage_client=None) -> StateRepository:
    return StateRepository(_FakeTenantScopedPool(conn), object_storage_client)


# -- decision_log_entries --------------------------------------------------


async def test_insert_decision_binds_all_columns_in_order() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)
    now = datetime.now(timezone.utc)

    entry = DecisionLogEntry(
        entry_id="entry-1",
        tenant_id=TENANT_ID,
        task_id="task-1",
        summary="summary",
        rationale="rationale",
        decided_by_kind="KIND_AGENT",
        decided_by_id="agent-1",
        decided_at=now,
        supersedes_entry_id="entry-0",
    )

    await repository.insert_decision(entry)

    _query, args = conn.executed[0]
    assert args == (
        "entry-1",
        TENANT_ID,
        "task-1",
        "summary",
        "rationale",
        "KIND_AGENT",
        "agent-1",
        now,
        "entry-0",
    )


async def test_get_decisions_by_task_maps_rows_to_dataclasses() -> None:
    now = datetime.now(timezone.utc)
    expected = DecisionLogEntry(
        entry_id="entry-1",
        tenant_id=TENANT_ID,
        task_id="task-1",
        summary="summary",
        rationale="rationale",
        decided_by_kind="KIND_AGENT",
        decided_by_id="agent-1",
        decided_at=now,
        supersedes_entry_id=None,
    )
    conn = _QueuedConnection(fetch_results=[[vars(expected)]])
    repository = make_repository(conn)

    entries = await repository.get_decisions_by_task("task-1")

    assert entries == [expected]


async def test_get_decisions_by_task_empty_when_no_rows() -> None:
    conn = _QueuedConnection(fetch_results=[[]])
    repository = make_repository(conn)

    assert await repository.get_decisions_by_task("task-1") == []


async def test_get_decisions_for_module_returns_empty_without_ownership_record() -> None:
    conn = _QueuedConnection(fetchrow_results=[None])
    repository = make_repository(conn)

    result = await repository.get_decisions_for_module(TENANT_ID, "state/app/repository.py")

    assert result == []


async def test_get_decisions_for_module_queries_last_touching_task() -> None:
    now = datetime.now(timezone.utc)
    ownership_record = OwnershipRecord(
        tenant_id=TENANT_ID,
        module_path="state/app/repository.py",
        last_task_id="task-1",
        last_agent_id="agent-1",
        last_touched_at=now,
    )
    expected_entry = DecisionLogEntry(
        entry_id="entry-1",
        tenant_id=TENANT_ID,
        task_id="task-1",
        summary="summary",
        rationale="rationale",
        decided_by_kind="KIND_AGENT",
        decided_by_id="agent-1",
        decided_at=now,
        supersedes_entry_id=None,
    )
    conn = _QueuedConnection(
        fetchrow_results=[vars(ownership_record)],
        fetch_results=[[vars(expected_entry)]],
    )
    repository = make_repository(conn)

    result = await repository.get_decisions_for_module(TENANT_ID, "state/app/repository.py")

    assert result == [expected_entry]
    # The second query was scoped to the ownership record's last_task_id,
    # not queried directly by module_path (decision_log_entries has no
    # module_path column -- see get_decisions_for_module's docstring).
    _query, args = conn.fetch_calls[0]
    assert args == ("task-1",)


# -- ownership_records --------------------------------------------------


async def test_upsert_ownership_binds_all_columns() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)
    now = datetime.now(timezone.utc)

    record = OwnershipRecord(
        tenant_id=TENANT_ID,
        module_path="state/app/repository.py",
        last_task_id="task-1",
        last_agent_id="agent-1",
        last_touched_at=now,
    )

    await repository.upsert_ownership(record)

    _query, args = conn.executed[0]
    assert args == (TENANT_ID, "state/app/repository.py", "task-1", "agent-1", now)
    assert "ON CONFLICT (tenant_id, module_path)" in _query
    assert "DO UPDATE SET" in _query


async def test_get_ownership_maps_row_to_dataclass() -> None:
    now = datetime.now(timezone.utc)
    expected = OwnershipRecord(
        tenant_id=TENANT_ID,
        module_path="state/app/repository.py",
        last_task_id="task-1",
        last_agent_id="agent-1",
        last_touched_at=now,
    )
    conn = _QueuedConnection(fetchrow_results=[vars(expected)])
    repository = make_repository(conn)

    record = await repository.get_ownership(TENANT_ID, "state/app/repository.py")

    assert record == expected


async def test_get_ownership_returns_none_when_absent() -> None:
    conn = _QueuedConnection(fetchrow_results=[None])
    repository = make_repository(conn)

    assert await repository.get_ownership(TENANT_ID, "missing.py") is None


# -- interface_contracts (schema_definition AS schema aliasing) -------------


async def test_get_contract_maps_schema_definition_column_alias() -> None:
    # what the SQL alias (schema_definition AS schema) yields
    expected = InterfaceContract(
        contract_id="contract-1",
        tenant_id=TENANT_ID,
        name="TaskNode",
        schema='{"v": 1}',
        version=1,
        frozen=False,
    )
    conn = _QueuedConnection(fetchrow_results=[vars(expected)])
    repository = make_repository(conn)

    contract = await repository.get_contract("contract-1")

    assert contract == expected
    assert contract is not None
    assert contract.schema == '{"v": 1}'


async def test_get_contract_returns_none_when_absent() -> None:
    conn = _QueuedConnection(fetchrow_results=[None])
    repository = make_repository(conn)

    assert await repository.get_contract("missing") is None


async def test_get_contract_version_maps_schema_definition_column_alias() -> None:
    expected = InterfaceContract(
        contract_id="contract-1",
        tenant_id=TENANT_ID,
        name="TaskNode",
        schema='{"v": 2}',
        version=2,
        frozen=True,
    )
    conn = _QueuedConnection(fetchrow_results=[vars(expected)])
    repository = make_repository(conn)

    contract = await repository.get_contract_version("contract-1", 2)

    assert contract == expected


async def test_save_contract_binds_schema_field_as_schema_definition_column() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)

    contract = InterfaceContract(
        contract_id="contract-1",
        tenant_id=TENANT_ID,
        name="TaskNode",
        schema='{"v": 1}',
        version=1,
        frozen=False,
    )

    await repository.save_contract(contract)

    query, args = conn.executed[0]
    assert "schema_definition" in query
    assert args == ("contract-1", TENANT_ID, "TaskNode", '{"v": 1}', 1, False)


# -- drift_reports --------------------------------------------------


async def test_insert_drift_report_binds_all_columns() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)

    report = DriftReport(
        report_id="report-1",
        tenant_id=TENANT_ID,
        contract_id="contract-1",
        description="drifted",
        resolved=False,
    )

    await repository.insert_drift_report(report)

    _query, args = conn.executed[0]
    assert args == ("report-1", TENANT_ID, "contract-1", "drifted", False)


async def test_get_drift_report_maps_row_to_dataclass() -> None:
    expected = DriftReport(
        report_id="report-1",
        tenant_id=TENANT_ID,
        contract_id="contract-1",
        description="drifted",
        resolved=False,
    )
    conn = _QueuedConnection(fetchrow_results=[vars(expected)])
    repository = make_repository(conn)

    report = await repository.get_drift_report("report-1")

    assert report == expected


async def test_get_drift_report_returns_none_when_absent() -> None:
    conn = _QueuedConnection(fetchrow_results=[None])
    repository = make_repository(conn)

    assert await repository.get_drift_report("missing") is None


async def test_update_drift_report_binds_report_id_description_resolved() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)

    report = DriftReport(
        report_id="report-1",
        tenant_id=TENANT_ID,
        contract_id="contract-1",
        description="resolved now",
        resolved=True,
    )

    await repository.update_drift_report(report)

    _query, args = conn.executed[0]
    assert args == ("report-1", "resolved now", True)


# -- module_states --------------------------------------------------


async def test_get_module_state_maps_schema_definition_column_alias() -> None:
    expected = ModuleState(
        tenant_id=TENANT_ID,
        module_path="state/app/repository.py",
        contract_id="contract-1",
        current_schema='{"v": 1}',
    )
    conn = _QueuedConnection(fetchrow_results=[vars(expected)])
    repository = make_repository(conn)

    state = await repository.get_module_state(TENANT_ID, "state/app/repository.py")

    assert state == expected


async def test_get_module_state_returns_none_when_absent() -> None:
    conn = _QueuedConnection(fetchrow_results=[None])
    repository = make_repository(conn)

    assert await repository.get_module_state(TENANT_ID, "missing.py") is None


async def test_save_module_state_binds_current_schema_as_schema_definition_column() -> None:
    conn = _QueuedConnection()
    repository = make_repository(conn)

    state = ModuleState(
        tenant_id=TENANT_ID,
        module_path="state/app/repository.py",
        contract_id="contract-1",
        current_schema='{"v": 1}',
    )

    await repository.save_module_state(state)

    query, args = conn.executed[0]
    assert "schema_definition" in query
    assert args == (TENANT_ID, "state/app/repository.py", "contract-1", '{"v": 1}')


# -- artifacts (object storage, not Postgres) --------------------------------


async def test_put_artifact_then_get_artifact_round_trips() -> None:
    object_storage_client = FakeObjectStorageClient()
    repository = StateRepository(pool=None, object_storage_client=object_storage_client)

    uri = await repository.put_artifact(TENANT_ID, "hydration-bundle.json", b'{"x": 1}')

    assert await repository.get_artifact(uri) == b'{"x": 1}'
    # tenant-prefixed key, matching ObjectStorageClient.put's real
    # tenant_id-kwarg behavior (see aecp_platform.storage.ObjectStorageClient).
    assert uri == f"{TENANT_ID}/hydration-bundle.json"
