"""Context hydration: builds the exact context bundle a new/resumed agent
session is allowed to see.

An agent should only ever need to look at
its own task node, its ownership boundary, and the State Layer's
contracts — never another agent's work directly. This module is
responsible for enforcing that boundary at hydration time, not trusting
the agent to self-limit.

Hydration reads only from data already captured on the AgentSession
record (task_node_snapshot, ownership_boundary — forwarded by the
Coordinator at spawn time, see docs/adr/0007-agent-pool-has-no-taskgraph-edge.md)
plus StateClient, since those are the only two dependencies
agents-edges.yaml's NetworkPolicy permits Agent Pool to reach.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextBundle:
    task_id: str
    task_node: bytes
    ownership_boundary: bytes
    relevant_interface_contracts: list[bytes]
    relevant_decision_log_entries: list[bytes]


class ContextHydrator:
    def __init__(self, lifecycle_manager, state_client) -> None:
        self.lifecycle_manager = lifecycle_manager
        # state_client is wired in ahead of proto/state/v1/state.proto
        # growing a query-by-task/module RPC for decision log entries and
        # interface contracts (StateService currently only exposes
        # GetInterfaceContract-by-exact-id and a write-only RecordDecision
        # — no "list what's relevant to task X"). Until that RPC exists,
        # relevant_interface_contracts/relevant_decision_log_entries below
        # are always empty; this is a documented contract gap, not a bug.
        self.state_client = state_client

    async def hydrate(self, session_id: str) -> ContextBundle:
        """Assemble the minimal context bundle needed to resume or start
        work on the task the given session owns: its own node, ownership
        boundary, and only the interface contracts / decision log entries
        relevant to it.
        """
        session = await self.lifecycle_manager.get(session_id)
        if session is None:
            raise LookupError(f"session '{session_id}' not found")

        return ContextBundle(
            task_id=session.task_id,
            task_node=session.task_node_snapshot,
            ownership_boundary=session.ownership_boundary,
            relevant_interface_contracts=[],
            relevant_decision_log_entries=[],
        )
