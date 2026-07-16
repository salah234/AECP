"""DAG model and dependency resolution over TaskNode.

Owns structural validity of the task graph: no cycles, no dangling
dependency references, and computing the "ready" frontier (nodes whose
dependencies are all DONE and are not themselves blocked).
"""

from __future__ import annotations

from .schema import TaskNode, TaskStatus
from collections import deque, defaultdict


class CycleDetectedError(Exception):
    """Raised when dependency graph contains a cycle."""

    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        dependency_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.dependency_id = dependency_id



class DanglingDependencyError(Exception):
    """Raised when a task node references a dependency that does not exist."""
    def __init__(self, task_id: str, dependency_id: str) -> None:
        super().__init__(
            f"Task '{task_id}' depends on unknown task '{dependency_id}'."
        )
        self.task_id = task_id
        self.dependency_id = dependency_id

class TaskGraph:
    """In-memory / query-backed view of one tenant's task DAG."""

    def __init__(self, repository) -> None:
        self.repository = repository

    async def add_node(self, node: TaskNode) -> TaskNode:
        """Insert a new task node after validating its dependencies exist
        and introduce no cycle.
        """
        for dependency_id in node.depends_on_task_ids:
            dependency = await self.repository.get(dependency_id)
            if dependency is None:
                raise DanglingDependencyError(node.task_id, dependency_id)

        await self.repository.create(node)

        try:
            await self.validate_acyclic(node.tenant_id)
        except CycleDetectedError:
            await self.repository.delete(node.task_id)
            raise

        return node


    async def ready_nodes(self, tenant_id: str) -> list[TaskNode]:
        """Return all nodes whose dependencies are all DONE and which are
        not BLOCKED.
        """
        nodes = await self.repository.list_by_tenant(tenant_id)
        node_map = {
            node.task_id: node for node in nodes
        }

        ready = []
        for node in nodes:
            if node.status == TaskStatus.BLOCKED:
                continue
                
            if node.status == TaskStatus.DONE:
                continue

            dep_done = all(
                node_map[dependency_id].status == TaskStatus.DONE 
                for dependency_id in node.depends_on_task_ids
                if dependency_id in node_map
            )

            if dep_done:
                ready.append(node)

        return ready

    async def validate_acyclic(self, tenant_id: str) -> None:
        """Raise CycleDetectedError if the current dependency graph for
        tenant_id contains a cycle.
        """
        
        nodes = await self.repository.list_by_tenant(tenant_id)
        node_map = {
            node.task_id: node for node in nodes
        }
        graph = defaultdict(list)
        indegree = {
            node.task_id: 0
            for node in nodes
        }
        for node in nodes: # Building Graph
            for dependency_id in node.depends_on_task_ids:
                graph[dependency_id].append(node.task_id)
                indegree[node.task_id] += 1
        
        queue = deque(
            node_id for node_id, degree in indegree.items()
            if degree == 0
        )

        processed = 0
        while queue:
            current_node = queue.popleft()
            processed += 1

            for neighbor in graph[current_node]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)
        
        if processed != len(nodes):
            raise CycleDetectedError(f'Cycle Detected for tenant {tenant_id}')
        else:
            print('Graph is Acyclic')
            


    async def dependents_of(self, task_id: str) -> list[TaskNode]:
        """Return nodes that list task_id in depends_on_task_ids."""
        
        nodes = await self.repository.list_dependents(task_id)
        return nodes
