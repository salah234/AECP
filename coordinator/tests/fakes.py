"""In-memory test doubles for coordinator components.

Used to exercise Scheduler/AssignmentEngine/TradeoffResolver/
CoordinatorServicer end-to-end against real domain logic without a live
Postgres connection, mTLS server, or gRPC connections to TaskGraph,
State, Agent Pool, Integration, or Observability.
"""

from __future__ import annotations

from uuid import uuid4

import grpc

from app.agents.v1 import agents_pb2
from app.common.v1 import common_pb2
from app.taskgraph.v1 import taskgraph_pb2


def _fake_rpc_error(code: grpc.StatusCode, details: str = "") -> grpc.aio.AioRpcError:
    """Build a real grpc.aio.AioRpcError so production `except
    grpc.aio.AioRpcError` clauses actually catch it — a fake exception
    type wouldn't be, since it isn't a subclass.
    """
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), details=details)


def make_task_node(
    *,
    task_id: str | None = None,
    tenant_id: str = "tenant-1",
    risk_tier=common_pb2.RISK_TIER_LOCAL,
    status=common_pb2.TASK_STATUS_PENDING,
    path_globs: list[str] | None = None,
    forbidden_globs: list[str] | None = None,
) -> taskgraph_pb2.TaskNode:
    node = taskgraph_pb2.TaskNode(
        task_id=task_id or str(uuid4()),
        tenant_id=tenant_id,
        title="Test task",
        description="A task used in coordinator tests",
        risk_tier=risk_tier,
        status=status,
        ownership=common_pb2.OwnershipBoundary(
            path_globs=path_globs or ["coordinator/app/**"],
            forbidden_globs=forbidden_globs or [],
        ),
    )
    return node


class FakeTaskGraphClient:
    """Implements the subset of TaskGraphClient's async interface that
    Scheduler/AssignmentEngine/TradeoffResolver depend on, backed by a
    plain dict of proto TaskNode messages.
    """

    def __init__(self, nodes: list[taskgraph_pb2.TaskNode] | None = None) -> None:
        self._nodes: dict[str, taskgraph_pb2.TaskNode] = {
            node.task_id: node for node in (nodes or [])
        }
        self.status_updates: list[tuple[str, int, str]] = []

    def add_node(self, node: taskgraph_pb2.TaskNode) -> None:
        self._nodes[node.task_id] = node

    async def list_ready_task_nodes(self, tenant_id: str) -> list[taskgraph_pb2.TaskNode]:
        return [
            node
            for node in self._nodes.values()
            if node.tenant_id == tenant_id
            and node.status == common_pb2.TASK_STATUS_PENDING
        ]

    async def get_task_node(
        self, task_id: str, tenant_id: str
    ) -> taskgraph_pb2.TaskNode | None:
        return self._nodes.get(task_id)

    async def update_task_status(self, task_id: str, tenant_id: str, status: int, reason: str):
        node = self._nodes.get(task_id)
        if node is None:
            raise KeyError(f"Task '{task_id}' not found.")

        updated = taskgraph_pb2.TaskNode()
        updated.CopyFrom(node)
        updated.status = status
        self._nodes[task_id] = updated
        self.status_updates.append((task_id, status, reason))
        return updated

    async def validate_ownership(self, task_id: str, tenant_id: str, changed_paths: list[str]):
        raise NotImplementedError("not exercised by current coordinator tests")


class FakeStateClient:
    def __init__(self, *, fail_record_decision: bool = False) -> None:
        self.recorded_decisions: list[dict] = []
        self.fail_record_decision = fail_record_decision

    async def record_decision(self, **kwargs):
        if self.fail_record_decision:
            raise _fake_rpc_error(grpc.StatusCode.UNAVAILABLE, "simulated State outage")
        self.recorded_decisions.append(kwargs)
        return kwargs

    async def get_ownership(self, tenant_id: str, module_path: str):
        return None

    async def get_interface_contract(self, contract_id: str):
        return None


class FakeAgentPoolClient:
    """Spawns fake sessions without any real sandbox/network call.

    fail_tenant_ids simulates Agent Pool being at capacity for specific
    tenants (RESOURCE_EXHAUSTED), so AssignmentEngine's per-task error
    isolation can be exercised.
    """

    def __init__(self, *, fail_tenant_ids: set[str] | None = None) -> None:
        self.spawned: list[dict] = []
        self.terminated: list[tuple[str, str]] = []
        self._fail_tenant_ids = fail_tenant_ids or set()
        self._sessions: list = []

    async def spawn_session(
        self, *, tenant_id, task_id, granted_risk_tier, ownership, task_node_snapshot
    ):
        if tenant_id in self._fail_tenant_ids:
            raise _fake_rpc_error(grpc.StatusCode.RESOURCE_EXHAUSTED, "pool at capacity")

        session = agents_pb2.AgentSession(
            session_id=f"session-{task_id}",
            tenant_id=tenant_id,
            task_id=task_id,
            status=agents_pb2.AGENT_SESSION_STATUS_ACTIVE,
            granted_risk_tier=granted_risk_tier,
            ownership=ownership,
            task_node_snapshot=task_node_snapshot,
        )
        self.spawned.append(
            {"tenant_id": tenant_id, "task_id": task_id, "session_id": session.session_id}
        )
        self._sessions.append(session)
        return session

    async def terminate_session(self, session_id: str, reason: str) -> bool:
        self.terminated.append((session_id, reason))
        return True

    async def list_sessions(self, tenant_id: str) -> list:
        return [s for s in self._sessions if s.tenant_id == tenant_id]


class FakeIntegrationClient:
    """detect_conflicts returns whatever `reports` was configured with —
    None simulates the real, not-yet-implemented IntegrationService
    (transport failure), matching integration_client.py's own contract.
    """

    def __init__(self, reports=None) -> None:
        self.reports = reports
        self.calls: list[tuple[str, list[str]]] = []

    async def detect_conflicts(self, tenant_id: str, candidate_task_ids: list[str]):
        self.calls.append((tenant_id, list(candidate_task_ids)))
        return self.reports


class FakeAuditClient:
    def __init__(self) -> None:
        self.recorded_events: list[dict] = []

    async def record_audit_event(self, **kwargs) -> bool:
        self.recorded_events.append(kwargs)
        return True


class AbortedRPC(Exception):
    """Raised by FakeContext.abort to mimic grpc.aio's abort-terminates-the-RPC
    semantics, so tests can assert on the status code that would have been
    sent to the caller.
    """

    def __init__(self, code, details: str = "") -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    async def abort(self, code, details: str = "") -> None:
        raise AbortedRPC(code, details)
