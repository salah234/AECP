"""Tests for SemanticDiffer's heuristic contradiction detection."""

from __future__ import annotations

from app.semantic_diff import SemanticDiffer

from .fakes import FakeStateClient, FakeTaskGraphClient, make_task_node

TENANT_ID = "tenant-1"


async def test_coherent_when_no_contradiction_signal() -> None:
    node_a = make_task_node(
        task_id="task-a",
        description="Add a caching layer in front of the database read path.",
        acceptance_criteria=["reads are cached for 60 seconds"],
    )
    node_b = make_task_node(
        task_id="task-b",
        description="Add structured logging to the ingestion pipeline.",
        acceptance_criteria=["logs are emitted as JSON"],
    )

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    differ = SemanticDiffer(FakeStateClient(), taskgraph_client)

    result = await differ.compare(TENANT_ID, "task-a", "task-b")

    assert result.jointly_coherent is True


async def test_flags_antonym_contradiction() -> None:
    node_a = make_task_node(
        task_id="task-a",
        description="The session refresh handler must be synchronous.",
    )
    node_b = make_task_node(
        task_id="task-b",
        description="The session refresh handler must be asynchronous.",
    )

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    differ = SemanticDiffer(FakeStateClient(), taskgraph_client)

    result = await differ.compare(TENANT_ID, "task-a", "task-b")

    assert result.jointly_coherent is False
    assert "synchronous" in result.explanation
    assert "asynchronous" in result.explanation


async def test_flags_negation_contradiction() -> None:
    node_a = make_task_node(
        task_id="task-a",
        acceptance_criteria=["the response payload must be idempotent"],
    )
    node_b = make_task_node(
        task_id="task-b",
        acceptance_criteria=["the response payload must not be idempotent"],
    )

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    differ = SemanticDiffer(FakeStateClient(), taskgraph_client)

    result = await differ.compare(TENANT_ID, "task-a", "task-b")

    assert result.jointly_coherent is False
    assert "idempotent" in result.explanation


async def test_coherent_when_task_missing() -> None:
    node_a = make_task_node(task_id="task-a", description="Something.")
    taskgraph_client = FakeTaskGraphClient([node_a])
    differ = SemanticDiffer(FakeStateClient(), taskgraph_client)

    result = await differ.compare(TENANT_ID, "task-a", "task-missing")

    assert result.jointly_coherent is True
    assert "task-missing" in result.explanation


async def test_ownership_context_note_uses_state_client_when_available() -> None:
    node_a = make_task_node(
        task_id="task-a",
        description="Unrelated change.",
        path_globs=["coordinator/app/scheduler.py"],
    )
    node_b = make_task_node(
        task_id="task-b",
        description="Another unrelated change.",
        path_globs=["coordinator/app/scheduler.py"],
    )

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])

    from app.state.v1 import state_pb2

    state_client = FakeStateClient(
        records={
            (TENANT_ID, "coordinator/app/scheduler.py"): state_pb2.OwnershipRecord(
                tenant_id=TENANT_ID,
                module_path="coordinator/app/scheduler.py",
                last_task_id="task-z",
            )
        }
    )
    differ = SemanticDiffer(state_client, taskgraph_client)

    result = await differ.compare(TENANT_ID, "task-a", "task-b")

    assert result.jointly_coherent is True
    assert "task-z" in result.explanation
    assert state_client.calls
