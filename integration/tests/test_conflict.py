"""Tests for ConflictDetector and app/ownership.py's overlap check."""

from __future__ import annotations

from app import ownership
from app.conflict import ConflictDetector, ConflictKind

from .fakes import FakeSemanticDiffer, FakeTaskGraphClient, make_task_node

TENANT_ID = "tenant-1"


# --- app/ownership.py: glob overlap, true/false cases ----------------------


def test_identical_globs_overlap() -> None:
    assert ownership.globs_may_overlap("integration/app/**", "integration/app/**") is True


def test_disjoint_top_level_globs_do_not_overlap() -> None:
    assert ownership.globs_may_overlap("coordinator/app/**", "taskgraph/app/**") is False


def test_wildcard_segment_within_shared_prefix_overlaps() -> None:
    assert ownership.globs_may_overlap("coordinator/app/*.py", "coordinator/app/scheduler.py") is True


def test_glob_with_no_literal_prefix_conservatively_overlaps() -> None:
    # "**" has no literal prefix at all -- conservatively treated as
    # capable of matching anything.
    assert ownership.globs_may_overlap("**", "taskgraph/app/graph.py") is True


def test_boundaries_may_overlap_true_when_any_pair_overlaps() -> None:
    assert ownership.boundaries_may_overlap(
        ["coordinator/app/scheduler.py", "coordinator/app/tradeoff.py"],
        ["taskgraph/app/**", "coordinator/app/*.py"],
    )


def test_boundaries_may_overlap_false_when_no_pair_overlaps() -> None:
    assert not ownership.boundaries_may_overlap(
        ["coordinator/app/**"],
        ["taskgraph/app/**", "state/app/**"],
    )


# --- ConflictDetector.detect: ownership ------------------------------------


async def test_detect_reports_ownership_conflict_for_overlapping_boundaries() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/*.py"])
    node_b = make_task_node(task_id="task-b", path_globs=["coordinator/app/scheduler.py"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])

    ownership_reports = [r for r in reports if r.kind == ConflictKind.OWNERSHIP]
    assert len(ownership_reports) == 1
    assert set(ownership_reports[0].task_ids) == {"task-a", "task-b"}
    assert ownership_reports[0].auto_resolvable is False
    assert ownership_reports[0].report_id
    assert ownership_reports[0].detected_at is not None


async def test_detect_reports_no_ownership_conflict_for_disjoint_boundaries() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["taskgraph/app/**"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])

    assert [r for r in reports if r.kind == ConflictKind.OWNERSHIP] == []


async def test_detect_skips_ownership_check_for_missing_task_node() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    taskgraph_client = FakeTaskGraphClient([node_a])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    # task-b was never registered with the fake client -> get_task_node
    # returns None for it, so no ownership report should be produced (no
    # data to compare against).
    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])

    assert [r for r in reports if r.kind == ConflictKind.OWNERSHIP] == []


# --- ConflictDetector.detect: textual (documented gap) ----------------------


async def test_detect_never_reports_textual_conflicts() -> None:
    """See conflict.py's _detect_textual docstring: no diff data source
    exists in the current data model, so this is always None -- a
    documented gap, not a silent "no conflict" default.
    """
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["coordinator/app/**"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    assert await detector._detect_textual("task-a", "task-b") is None

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])
    assert [r for r in reports if r.kind == ConflictKind.TEXTUAL] == []


# --- ConflictDetector.detect: semantic (via SemanticDiffer double) ---------


async def test_detect_reports_semantic_conflict_when_differ_flags_incoherent() -> None:
    from app.semantic_diff import SemanticDiffResult

    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["taskgraph/app/**"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    semantic_diff = FakeSemanticDiffer(
        results={
            ("task-a", "task-b"): SemanticDiffResult(
                jointly_coherent=False, explanation="contradiction found"
            )
        }
    )
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])

    semantic_reports = [r for r in reports if r.kind == ConflictKind.SEMANTIC]
    assert len(semantic_reports) == 1
    assert semantic_reports[0].description == "contradiction found"
    assert set(semantic_reports[0].task_ids) == {"task-a", "task-b"}


async def test_detect_reports_nothing_for_coherent_and_disjoint_pair() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["taskgraph/app/**"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b"])

    assert reports == []


async def test_detect_checks_every_pair_for_three_candidates() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["coordinator/app/**"])
    node_c = make_task_node(task_id="task-c", path_globs=["coordinator/app/**"])

    taskgraph_client = FakeTaskGraphClient([node_a, node_b, node_c])
    semantic_diff = FakeSemanticDiffer(default_coherent=True)
    detector = ConflictDetector(taskgraph_client, semantic_diff)

    reports = await detector.detect(TENANT_ID, ["task-a", "task-b", "task-c"])

    # 3 pairs, all overlapping ownership -> 3 ownership reports.
    ownership_reports = [r for r in reports if r.kind == ConflictKind.OWNERSHIP]
    assert len(ownership_reports) == 3
    assert len(semantic_diff.calls) == 3
