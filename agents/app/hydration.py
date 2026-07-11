"""Context hydration: builds the exact context bundle a new/resumed agent
session is allowed to see.

Per CLAUDE.md's key invariant, an agent should only ever need to look at
its own task node, its ownership boundary, and the State Layer's
contracts — never another agent's work directly. This module is
responsible for enforcing that boundary at hydration time, not trusting
the agent to self-limit.
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
    def __init__(self, taskgraph_client, state_client) -> None:
        raise NotImplementedError

    async def hydrate(self, session_id: str, task_id: str) -> ContextBundle:
        """Assemble the minimal context bundle needed to resume or start
        work on task_id: its own node, ownership boundary, and only the
        interface contracts / decision log entries relevant to it.
        """
        raise NotImplementedError
