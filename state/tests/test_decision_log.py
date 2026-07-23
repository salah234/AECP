"""Tests for DecisionLog.record/history_for_task/history_for_module against
FakeStateRepository.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

from app.decision_log import DecisionLog, DecisionLogEntry
from app.ownership_map import OwnershipRecord

from .fakes import FakeStateRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def make_entry(
    *,
    entry_id: str = "entry-1",
    task_id: str = "task-1",
    summary: str = "Chose Postgres for state layer",
    decided_at: datetime | None = None,
    supersedes_entry_id: str | None = None,
) -> DecisionLogEntry:
    return DecisionLogEntry(
        entry_id=entry_id,
        tenant_id=TENANT_ID,
        task_id=task_id,
        summary=summary,
        rationale="Full explanation goes here.",
        decided_by_kind="agent",  # DB's short form (grpc_server.py's _ACTOR_KIND_TO_DB), not the proto enum name
        decided_by_id="agent-42",
        decided_at=decided_at or datetime.now(UTC),
        supersedes_entry_id=supersedes_entry_id,
    )


async def test_record_appends_entry_without_mutating_existing() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    first = make_entry(entry_id="entry-1")
    await log.record(first)

    second = make_entry(entry_id="entry-2", supersedes_entry_id="entry-1")
    await log.record(second)

    assert repository.decisions == [first, second]


async def test_history_for_task_returns_only_that_tasks_entries_in_order() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    now = datetime.now(UTC)
    older = make_entry(entry_id="entry-1", task_id="task-1", decided_at=now)
    newer = make_entry(entry_id="entry-2", task_id="task-1", decided_at=now + timedelta(minutes=5))
    other_task = make_entry(entry_id="entry-3", task_id="task-2", decided_at=now)

    # Insert out of chronological order to prove ordering comes from
    # decided_at, not insertion order.
    await log.record(newer)
    await log.record(older)
    await log.record(other_task)

    history = await log.history_for_task("task-1")

    assert [entry.entry_id for entry in history] == ["entry-1", "entry-2"]


async def test_history_for_task_empty_when_no_entries() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    assert await log.history_for_task("no-such-task") == []


async def test_history_for_module_returns_last_touching_tasks_history() -> None:
    """Documented approximation (repository.get_decisions_for_module): module
    history is derived from whichever task last touched the module via
    ownership_records, not every task that ever touched it. This test
    asserts that actual, documented behavior rather than full multi-task
    history.
    """
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    entry_for_task_1 = make_entry(entry_id="entry-1", task_id="task-1")
    entry_for_task_2 = make_entry(entry_id="entry-2", task_id="task-2")
    await log.record(entry_for_task_1)
    await log.record(entry_for_task_2)

    # task-2 is the *last* task to touch the module.
    await repository.upsert_ownership(
        OwnershipRecord(
            tenant_id=TENANT_ID,
            module_path="state/app/repository.py",
            last_task_id="task-2",
            last_agent_id="agent-1",
            last_touched_at=datetime.now(UTC),
        )
    )

    history = await log.history_for_module(TENANT_ID, "state/app/repository.py")

    assert [entry.entry_id for entry in history] == ["entry-2"]


async def test_history_for_module_empty_list_when_no_ownership_record() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    await log.record(make_entry(entry_id="entry-1", task_id="task-1"))

    history = await log.history_for_module(TENANT_ID, "state/app/never_touched.py")

    assert history == []


async def test_history_for_module_only_reflects_last_touch_not_full_history() -> None:
    """Explicitly pins down the "not a bug" gap: even though task-1 also
    touched the module earlier (and has decisions of its own), once
    ownership moves to task-2 only task-2's history is visible.
    """
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    await log.record(make_entry(entry_id="entry-1", task_id="task-1"))
    await log.record(make_entry(entry_id="entry-2", task_id="task-2"))

    await repository.upsert_ownership(
        OwnershipRecord(
            tenant_id=TENANT_ID,
            module_path="state/app/repository.py",
            last_task_id="task-1",
            last_agent_id="agent-1",
            last_touched_at=datetime.now(UTC),
        )
    )
    first_pass = await log.history_for_module(TENANT_ID, "state/app/repository.py")
    assert [entry.entry_id for entry in first_pass] == ["entry-1"]

    await repository.upsert_ownership(
        OwnershipRecord(
            tenant_id=TENANT_ID,
            module_path="state/app/repository.py",
            last_task_id="task-2",
            last_agent_id="agent-2",
            last_touched_at=datetime.now(UTC),
        )
    )
    second_pass = await log.history_for_module(TENANT_ID, "state/app/repository.py")

    # entry-1 (task-1's decision) is no longer visible, even though task-1
    # really did touch this module at some point.
    assert [entry.entry_id for entry in second_pass] == ["entry-2"]


async def test_recent_returns_entries_newest_first() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    now = datetime.now(UTC)
    older = make_entry(entry_id="entry-1", task_id="task-1", decided_at=now)
    newer = make_entry(entry_id="entry-2", task_id="task-2", decided_at=now + timedelta(minutes=5))

    await log.record(older)
    await log.record(newer)

    recent = await log.recent(limit=50)

    assert [entry.entry_id for entry in recent] == ["entry-2", "entry-1"]


async def test_recent_respects_limit() -> None:
    repository = FakeStateRepository()
    log = DecisionLog(repository)

    now = datetime.now(UTC)
    for i in range(5):
        await log.record(make_entry(entry_id=f"entry-{i}", decided_at=now + timedelta(minutes=i)))

    recent = await log.recent(limit=2)

    assert [entry.entry_id for entry in recent] == ["entry-4", "entry-3"]
