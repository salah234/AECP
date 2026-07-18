from __future__ import annotations

import pytest

from app.scheduler import Scheduler
from tests.fakes import FakeIntegrationClient, FakeTaskGraphClient, make_task_node


@pytest.mark.asyncio
async def test_plan_tick_parallelizes_disjoint_ownership() -> None:
    node_a = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    node_b = make_task_node(path_globs=["taskgraph/app/graph.py"])
    taskgraph_client = FakeTaskGraphClient([node_a, node_b])

    scheduler = Scheduler(taskgraph_client)
    tick = await scheduler.plan_tick("tenant-1")

    assert set(tick.ready_task_ids) == {node_a.task_id, node_b.task_id}
    assert set(tick.parallelizable_task_ids) == {node_a.task_id, node_b.task_id}
    assert tick.serialized_task_ids == []


@pytest.mark.asyncio
async def test_plan_tick_serializes_overlapping_ownership() -> None:
    node_a = make_task_node(path_globs=["coordinator/app/**"])
    node_b = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    taskgraph_client = FakeTaskGraphClient([node_a, node_b])

    scheduler = Scheduler(taskgraph_client)
    tick = await scheduler.plan_tick("tenant-1")

    # Exactly one of the two overlapping tasks may be parallelizable this
    # tick; the other must be serialized (deferred), never both assigned.
    assert len(tick.parallelizable_task_ids) == 1
    assert len(tick.serialized_task_ids) == 1
    assert set(tick.parallelizable_task_ids) | set(tick.serialized_task_ids) == {
        node_a.task_id,
        node_b.task_id,
    }


@pytest.mark.asyncio
async def test_plan_tick_only_considers_the_requested_tenant() -> None:
    tenant_1_node = make_task_node(tenant_id="tenant-1")
    tenant_2_node = make_task_node(tenant_id="tenant-2")
    taskgraph_client = FakeTaskGraphClient([tenant_1_node, tenant_2_node])

    scheduler = Scheduler(taskgraph_client)
    tick = await scheduler.plan_tick("tenant-1")

    assert tick.ready_task_ids == [tenant_1_node.task_id]


@pytest.mark.asyncio
async def test_plan_tick_serializes_tasks_integration_reports_as_conflicting() -> None:
    node_a = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    node_b = make_task_node(path_globs=["taskgraph/app/graph.py"])
    taskgraph_client = FakeTaskGraphClient([node_a, node_b])

    class _Report:
        def __init__(self, task_ids):
            self.task_ids = task_ids

    integration_client = FakeIntegrationClient(reports=[_Report([node_a.task_id])])

    scheduler = Scheduler(taskgraph_client, integration_client)
    tick = await scheduler.plan_tick("tenant-1")

    assert node_a.task_id in tick.serialized_task_ids
    assert node_b.task_id in tick.parallelizable_task_ids


@pytest.mark.asyncio
async def test_plan_tick_degrades_gracefully_when_integration_unavailable() -> None:
    node_a = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    taskgraph_client = FakeTaskGraphClient([node_a])
    integration_client = FakeIntegrationClient(reports=None)  # simulates unavailable

    scheduler = Scheduler(taskgraph_client, integration_client)
    tick = await scheduler.plan_tick("tenant-1")

    assert tick.parallelizable_task_ids == [node_a.task_id]
    assert integration_client.calls == [("tenant-1", [node_a.task_id])]


@pytest.mark.asyncio
async def test_has_ownership_overlap_by_task_id() -> None:
    node_a = make_task_node(path_globs=["coordinator/app/**"])
    node_b = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    node_c = make_task_node(path_globs=["taskgraph/app/graph.py"])
    taskgraph_client = FakeTaskGraphClient([node_a, node_b, node_c])

    scheduler = Scheduler(taskgraph_client)

    assert await scheduler._has_ownership_overlap(node_a.task_id, node_b.task_id, "tenant-1") is True
    assert await scheduler._has_ownership_overlap(node_a.task_id, node_c.task_id, "tenant-1") is False


@pytest.mark.asyncio
async def test_has_ownership_overlap_raises_for_unknown_task() -> None:
    taskgraph_client = FakeTaskGraphClient([])
    scheduler = Scheduler(taskgraph_client)

    with pytest.raises(ValueError):
        await scheduler._has_ownership_overlap("missing-a", "missing-b", "tenant-1")
