"""DAG model and dependency resolution over TaskNode.

Owns structural validity of the task graph: no cycles, no dangling
dependency references, and computing the "ready" frontier (nodes whose
dependencies are all DONE and are not themselves blocked).
"""

from __future__ import annotations

from .schema import TaskNode


class CycleDetectedError(Exception):
    """Raised when adding/updating a dependency would create a cycle."""


class DanglingDependencyError(Exception):
    """Raised when a task node references a dependency that does not exist."""


class TaskGraph:
    """In-memory / query-backed view of one tenant's task DAG."""

    def __init__(self, repository) -> None:
        raise NotImplementedError

    async def add_node(self, node: TaskNode) -> TaskNode:
        """Insert a new task node after validating its dependencies exist
        and introduce no cycle.
        """
        raise NotImplementedError

    async def ready_nodes(self, tenant_id: str) -> list[TaskNode]:
        """Return all nodes whose dependencies are all DONE and which are
        not BLOCKED.
        """
        raise NotImplementedError

    async def validate_acyclic(self, tenant_id: str) -> None:
        """Raise CycleDetectedError if the current dependency graph for
        tenant_id contains a cycle.
        """
        raise NotImplementedError

    async def dependents_of(self, task_id: str) -> list[TaskNode]:
        """Return nodes that list task_id in depends_on_task_ids."""
        raise NotImplementedError
