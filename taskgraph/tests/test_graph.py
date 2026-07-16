"""Tests for TaskGraph: dependency validation, cycle detection + rollback,
and the ready-node frontier.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.graph import CycleDetectedError, DanglingDependencyError, TaskGraph
from app.schema import DefinitionOfDone, OwnershipBoundary, RiskTier, TaskNode, TaskStatus

from .fakes import FakeTaskNodeRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def make_node(task_id: str, depends_on: list[str] | None = None, status=TaskStatus.PENDING) -> TaskNode:
    now = datetime.now(timezone.utc)
    return TaskNode(
        task_id=task_id,
        tenant_id=TENANT_ID,
        title=task_id,
        description="",
        risk_tier=RiskTier.LOCAL,
        status=status,
        ownership=OwnershipBoundary(path_globs=["taskgraph/app/**"]),
        depends_on_task_ids=depends_on or [],
        definition_of_done=DefinitionOfDone(
            required_checks=[], acceptance_criteria=[], requires_human_review_gate=False
        ),
        created_at=now,
        updated_at=now,
    )


async def test_add_node_persists_via_repository() -> None:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)

    node = make_node("a")
    await graph.add_node(node)

    assert await repository.get("a") is not None


async def test_add_node_rejects_dangling_dependency_without_persisting() -> None:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)

    with pytest.raises(DanglingDependencyError):
        await graph.add_node(make_node("a", depends_on=["missing"]))

    assert await repository.get("a") is None


async def test_add_node_rolls_back_on_cycle_detected_across_tenant_graph() -> None:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)

    # Seed a pre-existing cycle directly (bypassing add_node's own
    # validation) to simulate a corrupted tenant graph, then confirm that
    # adding an unrelated, otherwise-valid new node is still rejected and
    # rolled back because validate_acyclic checks the whole tenant.
    await repository.create(make_node("x", depends_on=["y"]))
    await repository.create(make_node("y", depends_on=["x"]))

    with pytest.raises(CycleDetectedError):
        await graph.add_node(make_node("c"))

    assert await repository.get("c") is None
    # The pre-existing (unrelated) cyclic nodes are untouched by the rollback.
    assert await repository.get("x") is not None
    assert await repository.get("y") is not None


async def test_ready_nodes_excludes_blocked_and_done_and_unmet_dependencies() -> None:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)

    await graph.add_node(make_node("done", status=TaskStatus.DONE))
    await graph.add_node(make_node("blocked", status=TaskStatus.BLOCKED))
    await graph.add_node(make_node("ready-no-deps"))
    await graph.add_node(make_node("waiting", depends_on=["ready-no-deps"]))
    await graph.add_node(make_node("unblocked-by-done", depends_on=["done"]))

    ready_ids = {node.task_id for node in await graph.ready_nodes(TENANT_ID)}

    assert ready_ids == {"ready-no-deps", "unblocked-by-done"}


async def test_dependents_of_returns_nodes_depending_on_task() -> None:
    repository = FakeTaskNodeRepository()
    graph = TaskGraph(repository)

    await graph.add_node(make_node("a"))
    await graph.add_node(make_node("b", depends_on=["a"]))
    await graph.add_node(make_node("c", depends_on=["a"]))
    await graph.add_node(make_node("d"))

    dependents = {node.task_id for node in await graph.dependents_of("a")}

    assert dependents == {"b", "c"}
