"""In-memory test doubles for integration components.

Used to exercise ConflictDetector/SemanticDiffer/IntegrationServicer
end-to-end against real domain logic without a live gRPC connection to
TaskGraph or State.
"""

from __future__ import annotations

import grpc

from app.common.v1 import common_pb2
from app.state.v1 import state_pb2
from app.taskgraph.v1 import taskgraph_pb2


def _fake_rpc_error(code: grpc.StatusCode, details: str = "") -> grpc.aio.AioRpcError:
    """Build a real grpc.aio.AioRpcError so production `except
    grpc.aio.AioRpcError` clauses actually catch it — a fake exception
    type wouldn't be, since it isn't a subclass.
    """
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), details=details)


def make_task_node(
    *,
    task_id: str,
    tenant_id: str = "tenant-1",
    title: str = "Test task",
    description: str = "",
    acceptance_criteria: list[str] | None = None,
    risk_tier=common_pb2.RISK_TIER_LOCAL,
    path_globs: list[str] | None = None,
    forbidden_globs: list[str] | None = None,
) -> taskgraph_pb2.TaskNode:
    return taskgraph_pb2.TaskNode(
        task_id=task_id,
        tenant_id=tenant_id,
        title=title,
        description=description,
        risk_tier=risk_tier,
        status=common_pb2.TASK_STATUS_PENDING,
        ownership=common_pb2.OwnershipBoundary(
            path_globs=path_globs or ["integration/app/**"],
            forbidden_globs=forbidden_globs or [],
        ),
        definition_of_done=taskgraph_pb2.DefinitionOfDone(
            acceptance_criteria=acceptance_criteria or [],
        ),
    )


class FakeTaskGraphClient:
    """Implements the subset of TaskGraphClient's async interface that
    ConflictDetector/SemanticDiffer depend on, backed by a plain dict of
    proto TaskNode messages.
    """

    def __init__(self, nodes: list[taskgraph_pb2.TaskNode] | None = None) -> None:
        self._nodes: dict[str, taskgraph_pb2.TaskNode] = {
            node.task_id: node for node in (nodes or [])
        }
        self.calls: list[tuple[str, str]] = []

    def add_node(self, node: taskgraph_pb2.TaskNode) -> None:
        self._nodes[node.task_id] = node

    async def get_task_node(
        self, task_id: str, tenant_id: str
    ) -> taskgraph_pb2.TaskNode | None:
        self.calls.append((task_id, tenant_id))
        return self._nodes.get(task_id)


class FakeStateClient:
    """get_ownership returns whatever `records` was configured with for a
    given module_path, keyed as (tenant_id, module_path); missing keys
    return None (mirrors the real client's NOT_FOUND -> None mapping).
    """

    def __init__(self, records: dict[tuple[str, str], state_pb2.OwnershipRecord] | None = None) -> None:
        self._records = records or {}
        self.calls: list[tuple[str, str]] = []

    async def get_ownership(
        self, tenant_id: str, module_path: str
    ) -> state_pb2.OwnershipRecord | None:
        self.calls.append((tenant_id, module_path))
        return self._records.get((tenant_id, module_path))

    async def get_interface_contract(self, contract_id: str):
        raise NotImplementedError("not exercised by current integration tests")


class FakeSemanticDiffer:
    """Returns a fixed SemanticDiffResult (or one from `results`, keyed
    by the (task_id_a, task_id_b) pair) regardless of input, so
    ConflictDetector tests can isolate the ownership/textual checks from
    the semantic heuristic.
    """

    def __init__(self, *, default_coherent: bool = True, results=None) -> None:
        self.default_coherent = default_coherent
        self._results = results or {}
        self.calls: list[tuple[str, str, str]] = []

    async def compare(self, tenant_id: str, task_id_a: str, task_id_b: str):
        from app.semantic_diff import SemanticDiffResult

        self.calls.append((tenant_id, task_id_a, task_id_b))
        result = self._results.get((task_id_a, task_id_b))
        if result is not None:
            return result

        return SemanticDiffResult(
            jointly_coherent=self.default_coherent,
            explanation="fake differ default",
        )


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
