"""Tests for OwnershipMap.record_touch/get against FakeStateRepository."""

from __future__ import annotations

from app.ownership_map import OwnershipMap

from .fakes import FakeStateRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"
MODULE_PATH = "state/app/repository.py"


async def test_get_returns_none_when_never_touched() -> None:
    repository = FakeStateRepository()
    ownership_map = OwnershipMap(repository)

    assert await ownership_map.get(TENANT_ID, MODULE_PATH) is None


async def test_record_touch_then_get_round_trips() -> None:
    repository = FakeStateRepository()
    ownership_map = OwnershipMap(repository)

    await ownership_map.record_touch(
        tenant_id=TENANT_ID,
        module_path=MODULE_PATH,
        task_id="task-1",
        agent_id="agent-1",
    )

    record = await ownership_map.get(TENANT_ID, MODULE_PATH)

    assert record is not None
    assert record.tenant_id == TENANT_ID
    assert record.module_path == MODULE_PATH
    assert record.last_task_id == "task-1"
    assert record.last_agent_id == "agent-1"
    assert record.last_touched_at is not None


async def test_record_touch_upserts_and_overwrites_last_task_and_agent() -> None:
    """Touching the same module twice updates last_task_id/last_agent_id
    (upsert semantics), it does not accumulate history — that's the
    decision log's job, not the ownership map's.
    """
    repository = FakeStateRepository()
    ownership_map = OwnershipMap(repository)

    await ownership_map.record_touch(
        tenant_id=TENANT_ID,
        module_path=MODULE_PATH,
        task_id="task-1",
        agent_id="agent-1",
    )
    first_touch = await ownership_map.get(TENANT_ID, MODULE_PATH)
    assert first_touch is not None

    await ownership_map.record_touch(
        tenant_id=TENANT_ID,
        module_path=MODULE_PATH,
        task_id="task-2",
        agent_id="agent-2",
    )
    second_touch = await ownership_map.get(TENANT_ID, MODULE_PATH)

    assert second_touch is not None
    assert second_touch.last_task_id == "task-2"
    assert second_touch.last_agent_id == "agent-2"
    # Overwritten in place, not appended: only a single record exists for
    # this (tenant, module) pair.
    assert len(repository.ownership) == 1
    assert second_touch.last_touched_at >= first_touch.last_touched_at


async def test_record_touch_is_scoped_per_tenant() -> None:
    repository = FakeStateRepository()
    ownership_map = OwnershipMap(repository)

    other_tenant = "22222222-2222-2222-2222-222222222222"

    await ownership_map.record_touch(
        tenant_id=TENANT_ID,
        module_path=MODULE_PATH,
        task_id="task-1",
        agent_id="agent-1",
    )

    assert await ownership_map.get(other_tenant, MODULE_PATH) is None
    assert await ownership_map.get(TENANT_ID, MODULE_PATH) is not None
