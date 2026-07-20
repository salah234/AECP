"""Conflict logic must be tested with at least two concurrent agents
(see CLAUDE.md Development Workflow #2).

Two "agents" are simulated as two candidate task ids whose TaskNodes are
constructed with overlapping ownership boundaries AND contradictory
acceptance criteria (one asserts an invariant, the other negates it) --
each individually a perfectly valid task, but jointly incoherent, per
CLAUDE.md's own example ("two agents both 'fix' the same invariant in
incompatible ways"). Both the ownership check and the semantic heuristic
must catch this independently, and both must survive being run as truly
concurrent asyncio tasks (not just sequential awaits), matching
coordinator/tests/test_concurrent_agents.py's precedent for this
service.
"""

from __future__ import annotations

import asyncio

from app.conflict import ConflictDetector, ConflictKind
from app.semantic_diff import SemanticDiffer

from .fakes import FakeStateClient, FakeTaskGraphClient, make_task_node

TENANT_ID = "tenant-1"


def _make_conflicting_agent_nodes():
    """Two agents both "fixing" the same session-refresh invariant in
    incompatible ways, with overlapping ownership boundaries to boot
    (both declare they own the same file).
    """
    agent_a_node = make_task_node(
        task_id="agent-a-task",
        tenant_id=TENANT_ID,
        title="Make session refresh synchronous",
        description="The session refresh handler must be synchronous to avoid a race.",
        acceptance_criteria=["session refresh must be idempotent"],
        path_globs=["agents/app/session.py"],
    )
    agent_b_node = make_task_node(
        task_id="agent-b-task",
        tenant_id=TENANT_ID,
        title="Make session refresh asynchronous",
        description="The session refresh handler must be asynchronous for throughput.",
        acceptance_criteria=["session refresh must not be idempotent"],
        path_globs=["agents/app/session.py"],
    )
    return agent_a_node, agent_b_node


async def test_two_agents_editing_same_invariant_produce_semantic_conflict() -> None:
    """Two agents that each individually produce a valid diff, but whose
    diffs jointly contradict an invariant, must be reported as a semantic
    conflict rather than silently merged.
    """
    agent_a_node, agent_b_node = _make_conflicting_agent_nodes()
    taskgraph_client = FakeTaskGraphClient([agent_a_node, agent_b_node])
    semantic_differ = SemanticDiffer(FakeStateClient(), taskgraph_client)
    detector = ConflictDetector(taskgraph_client, semantic_differ)

    reports = await detector.detect(TENANT_ID, ["agent-a-task", "agent-b-task"])

    kinds = {report.kind for report in reports}
    assert ConflictKind.SEMANTIC in kinds, (
        "two agents contradicting the same invariant must be reported as a "
        "semantic conflict"
    )
    assert ConflictKind.OWNERSHIP in kinds, (
        "two agents declaring the same file in their ownership boundary "
        "must also be reported as an ownership conflict (defense in depth)"
    )

    semantic_report = next(r for r in reports if r.kind == ConflictKind.SEMANTIC)
    assert set(semantic_report.task_ids) == {"agent-a-task", "agent-b-task"}
    assert (
        "idempotent" in semantic_report.description
        or "synchronous" in semantic_report.description
    )


async def test_two_agents_run_as_genuinely_concurrent_asyncio_tasks() -> None:
    """Same scenario, but the two agents' work is dispatched as two
    concurrently-scheduled asyncio tasks (not sequential awaits) hitting
    a single shared SemanticDiffer/ConflictDetector pair -- the same
    sharing pattern IntegrationServicer uses for every DetectConflicts
    call it serves. This exercises that shared instances have no
    unsynchronized mutable state that a real concurrent scheduling tick
    could race on (see ConflictDetector's own docstring on why nodes are
    threaded through as explicit arguments instead of cached on self).
    """
    agent_a_node, agent_b_node = _make_conflicting_agent_nodes()
    taskgraph_client = FakeTaskGraphClient([agent_a_node, agent_b_node])
    semantic_differ = SemanticDiffer(FakeStateClient(), taskgraph_client)
    detector = ConflictDetector(taskgraph_client, semantic_differ)

    async def run_agent_a_side() -> list:
        return await detector.detect(TENANT_ID, ["agent-a-task", "agent-b-task"])

    async def run_agent_b_side() -> list:
        return await detector.detect(TENANT_ID, ["agent-b-task", "agent-a-task"])

    results_a, results_b = await asyncio.gather(run_agent_a_side(), run_agent_b_side())

    for reports in (results_a, results_b):
        kinds = {report.kind for report in reports}
        assert ConflictKind.SEMANTIC in kinds
        assert ConflictKind.OWNERSHIP in kinds
