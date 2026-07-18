"""Scheduling logic must be tested with at least two concurrent agents
(see CLAUDE.md Development Workflow #2). This is the required test; fill
in fixtures/assertions during implementation, do not delete or skip it.
"""

from __future__ import annotations

import asyncio

import pytest

from app.assignment import AssignmentEngine
from app.scheduler import Scheduler
from tests.fakes import FakeAgentPoolClient, FakeStateClient, FakeTaskGraphClient, make_task_node


@pytest.mark.asyncio
async def test_scheduler_does_not_double_assign_overlapping_ownership() -> None:
    """Two ready task nodes with overlapping ownership boundaries must
    never both be assigned in the same schedule tick.
    """
    task_a = make_task_node(path_globs=["coordinator/app/**"])
    task_b = make_task_node(path_globs=["coordinator/app/scheduler.py"])
    taskgraph_client = FakeTaskGraphClient([task_a, task_b])
    agent_pool_client = FakeAgentPoolClient()

    scheduler = Scheduler(taskgraph_client)
    assignment_engine = AssignmentEngine(agent_pool_client, FakeStateClient(), taskgraph_client)

    tick = await scheduler.plan_tick("tenant-1")
    decisions = await assignment_engine.assign(tick.parallelizable_task_ids, "tenant-1")

    assigned_task_ids = {decision.task_id for decision in decisions}
    assert task_a.task_id in assigned_task_ids or task_b.task_id in assigned_task_ids
    assert not {task_a.task_id, task_b.task_id}.issubset(assigned_task_ids), (
        "both overlapping-ownership tasks were assigned in the same tick"
    )
    assert len(agent_pool_client.spawned) == 1


@pytest.mark.asyncio
async def test_two_concurrent_agents_racing_the_same_tick_never_duplicate_assign() -> None:
    """Simulate two concurrent agents (two Schedule() calls racing on the
    same AssignmentEngine, e.g. a retried RPC) both trying to assign from
    the *same* computed tick. Regardless of interleaving, no task is ever
    spawned twice.

    Note on scope: this asserts the guarantee the system actually
    provides today — no double-*spawn* of the same task_id, whether the
    two calls race simultaneously (caught by AssignmentEngine's in-process
    _claiming set) or run sequentially (caught by the PENDING-status
    check in _assign_one, once the first call's update_task_status has
    landed). It deliberately does NOT assert that two *different*,
    overlapping-ownership tasks can never both end up ASSIGNED across two
    *separate* ticks over time — TaskGraphService has no RPC to list
    currently in-flight (ASSIGNED/IN_PROGRESS) nodes, only ready
    (PENDING) ones, so Coordinator has no way to check a new tick's
    candidates against work still active from a previous tick without
    that proto surface growing first. That's a real, separate follow-up,
    not something this test can responsibly assert against today.
    """
    task_a = make_task_node(path_globs=["coordinator/app/**"], tenant_id="tenant-1")
    task_b = make_task_node(path_globs=["coordinator/app/scheduler.py"], tenant_id="tenant-1")
    taskgraph_client = FakeTaskGraphClient([task_a, task_b])
    agent_pool_client = FakeAgentPoolClient()
    assignment_engine = AssignmentEngine(agent_pool_client, FakeStateClient(), taskgraph_client)

    scheduler = Scheduler(taskgraph_client)
    tick = await scheduler.plan_tick("tenant-1")
    assert len(tick.parallelizable_task_ids) == 1, "sanity: overlap must serialize one of the two"

    # Two concurrent "agents" both racing to process the SAME tick output
    # (e.g. duplicate delivery of a Schedule response to two workers).
    results = await asyncio.gather(
        assignment_engine.assign(tick.parallelizable_task_ids, "tenant-1"),
        assignment_engine.assign(tick.parallelizable_task_ids, "tenant-1"),
    )
    all_decisions = [decision for batch in results for decision in batch]
    assigned_task_ids = [decision.task_id for decision in all_decisions]

    assert len(assigned_task_ids) == 1, "the same tick's task was spawned more than once"
    assert len(agent_pool_client.spawned) == 1


@pytest.mark.asyncio
async def test_concurrent_assign_calls_never_double_spawn_the_same_task() -> None:
    """Directly race two assign() calls over the *same* single ready task
    (e.g. two Coordinator replicas both handling a retry). The in-process
    claim guard must ensure only one spawn happens.
    """
    task = make_task_node(tenant_id="tenant-1")
    taskgraph_client = FakeTaskGraphClient([task])
    agent_pool_client = FakeAgentPoolClient()
    assignment_engine = AssignmentEngine(agent_pool_client, FakeStateClient(), taskgraph_client)

    results = await asyncio.gather(
        assignment_engine.assign([task.task_id], "tenant-1"),
        assignment_engine.assign([task.task_id], "tenant-1"),
    )

    successful = [d for batch in results for d in batch]
    assert len(successful) == 1, "the same task was spawned by both concurrent assign() calls"
    assert len(agent_pool_client.spawned) == 1


@pytest.mark.asyncio
async def test_concurrent_ticks_respect_per_tenant_isolation() -> None:
    """Two concurrent agents scheduling for two different tenants must
    never interfere with each other's ready sets."""
    tenant_1_task = make_task_node(tenant_id="tenant-1")
    tenant_2_task = make_task_node(tenant_id="tenant-2")
    taskgraph_client = FakeTaskGraphClient([tenant_1_task, tenant_2_task])
    agent_pool_client = FakeAgentPoolClient()

    scheduler = Scheduler(taskgraph_client)
    assignment_engine = AssignmentEngine(agent_pool_client, FakeStateClient(), taskgraph_client)

    async def run_tick(tenant_id: str):
        tick = await scheduler.plan_tick(tenant_id)
        return await assignment_engine.assign(tick.parallelizable_task_ids, tenant_id)

    results = await asyncio.gather(run_tick("tenant-1"), run_tick("tenant-2"))

    assigned_task_ids = {decision.task_id for batch in results for decision in batch}
    assert assigned_task_ids == {tenant_1_task.task_id, tenant_2_task.task_id}
