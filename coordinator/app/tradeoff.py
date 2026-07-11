"""Cross-agent tradeoff resolution and escalation handling.

Handles the Escalate RPC: an agent that discovers a task is bigger than
its granted risk tier halts and calls this instead of proceeding on its
own judgment. This module decides whether to auto-approve a tier bump
(never above what the task graph's own policy allows) or to route to a
human via the observability escalation queue.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EscalationDecision:
    task_id: str
    approved: bool
    decided_by: str


class TradeoffResolver:
    """Owns cross-agent tradeoff decisions: escalations, blocker
    reports, and any judgment call that would otherwise require two
    agents to coordinate directly.
    """

    def __init__(self, state_client, observability_client) -> None:
        raise NotImplementedError

    async def escalate(
        self, task_id: str, agent_id: str, reason: str, requested_risk_tier: int
    ) -> EscalationDecision:
        """Decide whether a requested risk-tier bump can be auto-approved
        or must block on a human reviewer.
        """
        raise NotImplementedError

    async def report_blocker(self, task_id: str, agent_id: str, description: str) -> None:
        """Record a blocker report and determine whether it changes
        scheduling for dependent task nodes.
        """
        raise NotImplementedError
