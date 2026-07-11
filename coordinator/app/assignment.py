"""Assignment: picks which agent (or agent pool slot) takes each ready task.

Grants a risk tier no higher than the task node's own tier. An agent must
never self-assign a higher tier than the task graph gave it; this module
is where that grant is made and recorded, not the agent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AssignmentDecision:
    task_id: str
    agent_id: str
    granted_risk_tier: int
    rationale: str


class AssignmentEngine:
    """Maps ready, schedulable task nodes to available agent pool
    capacity via the Agent Pool service.
    """

    def __init__(self, agent_pool_client, state_client) -> None:
        raise NotImplementedError

    async def assign(self, task_ids: list[str], tenant_id: str) -> list[AssignmentDecision]:
        """Produce assignment decisions for the given ready task ids,
        spawning agent sessions as needed via the Agent Pool service.
        """
        raise NotImplementedError
