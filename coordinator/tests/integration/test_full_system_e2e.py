"""System-wide integration/regression tests against the real Docker
topology in docker-compose.test.yml, extending test_e2e_docker_compose.py's
coverage to integration, observability, and gateway now that all three are
real services rather than the unimplemented stubs this topology used to
omit. Same opt-in gating as that file — see its module docstring for how
to boot the stack and apply migrations first.

The single most important test here is
test_coordinator_schedule_serializes_conflicting_tasks_via_real_integration_service:
before this session, Coordinator's IntegrationClient always talked to an
address with nothing listening on it, so Scheduler's conflict-aware
partitioning was only ever exercised via the *graceful-degradation* path
(treat "no response" as "no additional conflicts"). This is the first test
that proves the real request/response round-trip between Coordinator and
Integration actually works.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import grpc
import pytest

from app.common.v1 import common_pb2
from app.coordinator.v1 import coordinator_pb2, coordinator_pb2_grpc
from app.integration.v1 import integration_pb2, integration_pb2_grpc
from app.observability.v1 import observability_pb2, observability_pb2_grpc
from app.taskgraph.v1 import taskgraph_pb2, taskgraph_pb2_grpc

from .test_e2e_docker_compose import _wait_for_channel_ready

pytestmark = pytest.mark.skipif(
    os.getenv("AECP_RUN_DOCKER_INTEGRATION_TESTS") != "1",
    reason="opt-in: set AECP_RUN_DOCKER_INTEGRATION_TESTS=1 and boot "
    "docker-compose.test.yml first (see test_e2e_docker_compose.py's module docstring)",
)

TASKGRAPH_ADDR = "localhost:55052"
COORDINATOR_ADDR = "localhost:55054"
INTEGRATION_ADDR = "localhost:55055"
OBSERVABILITY_ADDR = "localhost:55056"
GATEWAY_HTTP_ADDR = "http://localhost:58084"


def _caller_metadata(caller_id: str) -> tuple[tuple[str, str], ...]:
    return (("caller-id", caller_id),)


@pytest.fixture(scope="module", autouse=True)
def _wait_for_stack_ready():
    import asyncio

    async def wait_all():
        await asyncio.gather(
            _wait_for_channel_ready(TASKGRAPH_ADDR),
            _wait_for_channel_ready(COORDINATOR_ADDR),
            _wait_for_channel_ready(INTEGRATION_ADDR),
            _wait_for_channel_ready(OBSERVABILITY_ADDR),
        )

    asyncio.run(wait_all())


@pytest.fixture(scope="module")
def tenant_id() -> str:
    return str(uuid4())


async def _create_task(
    tenant_id: str,
    *,
    title: str,
    path_globs: list[str],
    risk_tier=common_pb2.RISK_TIER_LOCAL,
    acceptance_criteria: list[str] | None = None,
) -> str:
    async with grpc.aio.insecure_channel(TASKGRAPH_ADDR) as channel:
        stub = taskgraph_pb2_grpc.TaskGraphServiceStub(channel)
        response = await stub.CreateTaskNode(
            taskgraph_pb2.CreateTaskNodeRequest(
                node=taskgraph_pb2.TaskNode(
                    tenant_id=tenant_id,
                    title=title,
                    risk_tier=risk_tier,
                    status=common_pb2.TASK_STATUS_PENDING,
                    ownership=common_pb2.OwnershipBoundary(path_globs=path_globs),
                    definition_of_done=taskgraph_pb2.DefinitionOfDone(
                        acceptance_criteria=acceptance_criteria or [],
                    ),
                )
            ),
            metadata=_caller_metadata("coordinator"),
        )
        return response.node.task_id


@pytest.mark.asyncio
async def test_integration_detects_ownership_conflict_across_real_services(
    tenant_id: str,
) -> None:
    task_a = await _create_task(
        tenant_id, title="Refactor billing client", path_globs=["services/billing/**"]
    )
    task_b = await _create_task(
        tenant_id, title="Add billing retry logic", path_globs=["services/billing/client.py"]
    )

    async with grpc.aio.insecure_channel(INTEGRATION_ADDR) as channel:
        stub = integration_pb2_grpc.IntegrationServiceStub(channel)
        response = await stub.DetectConflicts(
            integration_pb2.DetectConflictsRequest(
                tenant_id=tenant_id, candidate_task_ids=[task_a, task_b]
            ),
            metadata=_caller_metadata("coordinator"),
        )

    kinds = {report.kind for report in response.reports}
    assert integration_pb2.CONFLICT_KIND_OWNERSHIP in kinds, (
        f"expected an OWNERSHIP conflict between overlapping billing/** paths, got: "
        f"{[integration_pb2.ConflictKind.Name(r.kind) for r in response.reports]}"
    )


@pytest.mark.asyncio
async def test_integration_resolve_merge_policy_requires_human_for_ownership_conflict(
    tenant_id: str,
) -> None:
    task_a = await _create_task(
        tenant_id, title="Touch shared config A", path_globs=["services/shared/config.py"]
    )
    task_b = await _create_task(
        tenant_id, title="Touch shared config B", path_globs=["services/shared/config.py"]
    )

    async with grpc.aio.insecure_channel(INTEGRATION_ADDR) as channel:
        stub = integration_pb2_grpc.IntegrationServiceStub(channel)
        detect_response = await stub.DetectConflicts(
            integration_pb2.DetectConflictsRequest(
                tenant_id=tenant_id, candidate_task_ids=[task_a, task_b]
            ),
            metadata=_caller_metadata("coordinator"),
        )
        ownership_reports = [
            r for r in detect_response.reports if r.kind == integration_pb2.CONFLICT_KIND_OWNERSHIP
        ]
        assert ownership_reports, "expected at least one ownership conflict report to resolve"

        resolve_response = await stub.ResolveMergePolicy(
            integration_pb2.ResolveMergePolicyRequest(
                report_id=ownership_reports[0].report_id,
                risk_tier=common_pb2.RISK_TIER_MECHANICAL,
            ),
            metadata=_caller_metadata("coordinator"),
        )

    # Per merge_policy.py's POLICY_TABLE: ownership conflicts always
    # require human review regardless of risk tier — even at the lowest
    # (mechanical) tier, which is the strongest case to prove the table
    # isn't just defaulting to "auto-merge everything low-risk".
    assert resolve_response.decision.requires_human is True
    assert resolve_response.decision.auto_merge is False


@pytest.mark.asyncio
async def test_integration_semantic_diff_flags_contradictory_acceptance_criteria(
    tenant_id: str,
) -> None:
    task_a = await _create_task(
        tenant_id,
        title="Implement webhook handler",
        path_globs=["services/webhooks/**"],
        acceptance_criteria=["handler must be idempotent"],
    )
    task_b = await _create_task(
        tenant_id,
        title="Implement webhook retry",
        path_globs=["services/webhooks/**"],
        acceptance_criteria=["retry logic must not be idempotent"],
    )

    async with grpc.aio.insecure_channel(INTEGRATION_ADDR) as channel:
        stub = integration_pb2_grpc.IntegrationServiceStub(channel)
        response = await stub.SemanticDiff(
            integration_pb2.SemanticDiffRequest(
                tenant_id=tenant_id, task_id_a=task_a, task_id_b=task_b
            ),
            metadata=_caller_metadata("coordinator"),
        )

    assert response.jointly_coherent is False
    assert response.explanation


@pytest.mark.asyncio
async def test_observability_records_and_queries_a_real_audit_event(tenant_id: str) -> None:
    event = common_pb2.AuditEvent(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        actor=common_pb2.Actor(kind=common_pb2.Actor.KIND_HUMAN, id="em-system-test"),
        action="system_e2e_test",
        resource="test:full_system_e2e",
        security_relevant=True,
    )
    event.occurred_at.FromDatetime(datetime.now(timezone.utc))

    async with grpc.aio.insecure_channel(OBSERVABILITY_ADDR) as channel:
        stub = observability_pb2_grpc.AuditServiceStub(channel)
        record_response = await stub.RecordAuditEvent(
            observability_pb2.RecordAuditEventRequest(event=event),
            metadata=_caller_metadata("coordinator"),
        )
        assert record_response.event_id == event.event_id

        query_response = await stub.QueryAuditEvents(
            observability_pb2.QueryAuditEventsRequest(
                tenant_id=tenant_id, security_relevant_only=True
            ),
            metadata=_caller_metadata("coordinator"),
        )

    recorded_ids = {e.event_id for e in query_response.events}
    assert event.event_id in recorded_ids


@pytest.mark.asyncio
async def test_coordinator_schedule_serializes_conflicting_tasks_via_real_integration_service(
    tenant_id: str,
) -> None:
    """The key regression this session closes: Coordinator's
    IntegrationClient used to talk to an address nothing was listening on,
    so this partitioning logic only ever ran its graceful-degradation path
    ("no response" -> "no additional conflicts known"). With a real
    Integration container in the topology, a tenant with two tasks that
    conflict must now see that reflected in Schedule's real output.

    Per scheduler.py's plan_tick: an Integration-reported conflict adds
    every task_id in that report to conflicted_task_ids, and *all* of them
    are serialized this tick — deliberately more conservative than the
    local ownership-overlap check just below it, which lets the
    first-claimed task through while serializing the rest. So the
    observable effect of a real (vs. gracefully-degraded/absent)
    Integration response here is that *neither* conflicting task is
    assigned this tick, not "exactly one."
    """
    task_a = await _create_task(
        tenant_id, title="Edit rate limiter A", path_globs=["services/ratelimit/**"]
    )
    task_b = await _create_task(
        tenant_id, title="Edit rate limiter B", path_globs=["services/ratelimit/**"]
    )

    async with grpc.aio.insecure_channel(COORDINATOR_ADDR) as channel:
        stub = coordinator_pb2_grpc.CoordinatorServiceStub(channel)
        response = await stub.Schedule(
            coordinator_pb2.ScheduleRequest(tenant_id=tenant_id),
            metadata=_caller_metadata("test-client"),
        )

    assigned_ids = {d.task_id for d in response.decisions}
    assert task_a not in assigned_ids and task_b not in assigned_ids, (
        "expected both conflicting tasks to be held back this tick per "
        "Integration's real conflict report, but at least one was assigned: "
        f"{assigned_ids}"
    )


def test_gateway_health_and_auth_enforcement_over_real_network() -> None:
    """Lightweight on purpose: gateway/tests/ already covers its REST/auth
    logic thoroughly against fakes (40 cases). What this system test
    uniquely adds is proof that the real container is reachable and wired
    up over the real Docker network — not a re-test of gateway's internals.
    """
    import urllib.error
    import urllib.request

    with urllib.request.urlopen(f"{GATEWAY_HTTP_ADDR}/healthz", timeout=10) as response:
        assert response.status == 200

    with urllib.request.urlopen(f"{GATEWAY_HTTP_ADDR}/readyz", timeout=10) as response:
        assert response.status == 200

    try:
        urllib.request.urlopen(f"{GATEWAY_HTTP_ADDR}/api/v1/tasks", timeout=10)
        assert False, "expected /api/v1/tasks without a session cookie to be rejected"
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
