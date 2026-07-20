"""Integration-style tests for IntegrationServicer against real
ConflictDetector/MergePolicyResolver/SemanticDiffer logic, backed by
in-memory fakes (see tests/fakes.py) instead of live TaskGraph/State
connections.
"""

from __future__ import annotations

import grpc
import pytest

from app.common.v1 import common_pb2
from app.conflict import ConflictDetector
from app.grpc_server import IntegrationServicer
from app.integration.v1 import integration_pb2
from app.merge_policy import MergePolicyResolver
from app.semantic_diff import SemanticDiffer

from .fakes import AbortedRPC, FakeContext, FakeStateClient, FakeTaskGraphClient, make_task_node

TENANT_ID = "tenant-1"


def make_servicer(nodes=None) -> tuple[IntegrationServicer, FakeTaskGraphClient]:
    taskgraph_client = FakeTaskGraphClient(nodes or [])
    state_client = FakeStateClient()
    semantic_differ = SemanticDiffer(state_client, taskgraph_client)
    conflict_detector = ConflictDetector(taskgraph_client, semantic_differ)
    merge_policy_resolver = MergePolicyResolver()

    servicer = IntegrationServicer(
        conflict_detector=conflict_detector,
        merge_policy_resolver=merge_policy_resolver,
        semantic_differ=semantic_differ,
    )
    return servicer, taskgraph_client


async def test_detect_conflicts_reports_ownership_overlap() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["coordinator/app/scheduler.py"])
    servicer, _ = make_servicer([node_a, node_b])
    context = FakeContext()

    response = await servicer.DetectConflicts(
        integration_pb2.DetectConflictsRequest(
            tenant_id=TENANT_ID, candidate_task_ids=["task-a", "task-b"]
        ),
        context,
    )

    assert len(response.reports) == 1
    assert response.reports[0].kind == integration_pb2.CONFLICT_KIND_OWNERSHIP
    assert set(response.reports[0].task_ids) == {"task-a", "task-b"}
    assert response.reports[0].report_id


async def test_detect_conflicts_requires_tenant_id() -> None:
    servicer, _ = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.DetectConflicts(
            integration_pb2.DetectConflictsRequest(candidate_task_ids=["task-a"]), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_resolve_merge_policy_round_trips_cached_report() -> None:
    node_a = make_task_node(task_id="task-a", path_globs=["coordinator/app/**"])
    node_b = make_task_node(task_id="task-b", path_globs=["coordinator/app/scheduler.py"])
    servicer, _ = make_servicer([node_a, node_b])
    context = FakeContext()

    detect_response = await servicer.DetectConflicts(
        integration_pb2.DetectConflictsRequest(
            tenant_id=TENANT_ID, candidate_task_ids=["task-a", "task-b"]
        ),
        context,
    )
    report_id = detect_response.reports[0].report_id

    resolve_response = await servicer.ResolveMergePolicy(
        integration_pb2.ResolveMergePolicyRequest(
            report_id=report_id, risk_tier=common_pb2.RISK_TIER_STRUCTURAL
        ),
        context,
    )

    # Ownership conflicts always require human review regardless of tier.
    assert resolve_response.decision.report_id == report_id
    assert resolve_response.decision.requires_human is True
    assert resolve_response.decision.auto_merge is False


async def test_resolve_merge_policy_not_found_for_unknown_report_id() -> None:
    servicer, _ = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.ResolveMergePolicy(
            integration_pb2.ResolveMergePolicyRequest(
                report_id="does-not-exist", risk_tier=common_pb2.RISK_TIER_MECHANICAL
            ),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


async def test_semantic_diff_rpc_returns_differ_result() -> None:
    node_a = make_task_node(task_id="task-a", description="Must be synchronous.")
    node_b = make_task_node(task_id="task-b", description="Must be asynchronous.")
    servicer, _ = make_servicer([node_a, node_b])
    context = FakeContext()

    response = await servicer.SemanticDiff(
        integration_pb2.SemanticDiffRequest(
            tenant_id=TENANT_ID, task_id_a="task-a", task_id_b="task-b"
        ),
        context,
    )

    assert response.jointly_coherent is False
    assert "synchronous" in response.explanation


async def test_semantic_diff_requires_tenant_id() -> None:
    servicer, _ = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.SemanticDiff(
            integration_pb2.SemanticDiffRequest(task_id_a="task-a", task_id_b="task-b"), context
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT
