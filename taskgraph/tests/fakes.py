"""In-memory test doubles for taskgraph components.

Used to exercise TaskGraphServicer end-to-end against real TaskGraph and
ownership logic without a live Postgres connection or mTLS server.
"""

from __future__ import annotations

from app.schema import TaskNode, TaskStatus


class FakeTaskNodeRepository:
    """Implements the subset of TaskNodeRepository's async interface that
    TaskGraph and TaskGraphServicer depend on, backed by a plain dict.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}

    async def create(self, node: TaskNode) -> TaskNode:
        self._nodes[node.task_id] = node
        return node

    async def get(self, task_id: str) -> TaskNode | None:
        return self._nodes.get(task_id)

    async def update_status(self, task_id: str, status: TaskStatus, reason: str) -> TaskNode:
        node = self._nodes.get(task_id)
        if node is None:
            raise KeyError(f"Task '{task_id}' not found.")

        updated = node.model_copy(update={"status": status})
        self._nodes[task_id] = updated
        return updated

    async def list_by_tenant(self, tenant_id: str) -> list[TaskNode]:
        return [node for node in self._nodes.values() if node.tenant_id == tenant_id]

    async def list_ready(self, tenant_id: str) -> list[TaskNode]:
        raise NotImplementedError("servicer uses TaskGraph.ready_nodes, not this query path")

    async def list_dependents(self, task_id: str) -> list[TaskNode]:
        return [
            node
            for node in self._nodes.values()
            if task_id in node.depends_on_task_ids
        ]

    async def list_dependencies(self, task_id: str) -> list[str]:
        node = self._nodes.get(task_id)
        return list(node.depends_on_task_ids) if node else []

    async def delete(self, task_id: str) -> None:
        self._nodes.pop(task_id, None)


class AbortedRPC(Exception):
    """Raised by FakeContext.abort to mimic grpc.aio's abort-terminates-the-RPC
    semantics, so tests can assert on the status code that would have been
    sent to the caller.
    """

    def __init__(self, code, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    async def abort(self, code, details: str = "") -> None:
        raise AbortedRPC(code, details)
