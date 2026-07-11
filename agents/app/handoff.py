"""Handoff protocol: transferring an in-progress task to a new agent
session instance without loss of continuity.

Triggered by lifecycle.reap_expired, an explicit agent-requested handoff,
or a Coordinator-directed reassignment. The new session must rehydrate
from the State Layer exactly as a first-time session would — handoff
never copies scratch context directly between sessions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import AgentSession


@dataclass
class HandoffRecord:
    old_session_id: str
    new_session_id: str
    reason: str


class HandoffCoordinator:
    def __init__(self, lifecycle_manager, hydrator, state_client) -> None:
        raise NotImplementedError

    async def handoff(self, session_id: str, reason: str) -> AgentSession:
        """Terminate the old session, record the handoff in the decision
        log, spawn a replacement session for the same task, and return it.
        """
        raise NotImplementedError
