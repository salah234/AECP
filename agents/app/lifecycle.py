"""Agent session lifecycle: spawn, monitor, terminate.

Owns the AgentSession record's existence and its granted risk tier. Never
grants a tier higher than the task node's own tier — that check is
delegated to taskgraph.risk_tier via the State/TaskGraph clients, not
re-implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentSession:
    session_id: str
    tenant_id: str
    task_id: str
    status: str
    granted_risk_tier: str


class LifecycleManager:
    def __init__(self, taskgraph_client, sandbox, identity_issuer) -> None:
        raise NotImplementedError

    async def spawn(self, tenant_id: str, task_id: str, granted_risk_tier: str) -> AgentSession:
        """Create a new sandboxed agent session scoped to exactly one task
        node and its ownership boundary.
        """
        raise NotImplementedError

    async def terminate(self, session_id: str, reason: str) -> None:
        """Tear down a session's sandbox and revoke its scoped credentials."""
        raise NotImplementedError

    async def reap_expired(self) -> list[str]:
        """Find and terminate sessions past their TTL; return their ids so
        the Coordinator can be notified to re-schedule their tasks.
        """
        raise NotImplementedError
