"""Agent session lifecycle: spawn, monitor, terminate.

Owns the AgentSession record's existence and its granted risk tier. Never
grants a tier higher than the task node's own tier — but that check
happens one level up, in the Coordinator, not here: Agent Pool has no
network or client edge to TaskGraphService
(deploy/k8s/networkpolicy/agents-edges.yaml), so it cannot re-derive a
task's risk tier itself. It trusts the granted_risk_tier the Coordinator
asserts at spawn time (Coordinator is itself mTLS-authenticated as a
trusted internal service) and, per CLAUDE.md, never lets that grant be
silently escalated afterwards — an agent that discovers a task is bigger
than its tier must halt and re-escalate to the Coordinator
(CoordinatorService.Escalate), not act at its own judgment. See
docs/adr/0007-agent-pool-has-no-taskgraph-edge.md.

Sessions are disposable and stateless by design (CLAUDE.md): the registry
here is in-memory only, not backed by Postgres. All durable knowledge
(decisions, ownership history) lives in the State Layer; this registry
only needs to survive for a single session's TTL, and a process restart
correctly discards it along with every sandbox it was tracking.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass
class AgentSession:
    session_id: str
    tenant_id: str
    task_id: str
    status: str
    granted_risk_tier: str
    ownership_boundary: bytes = field(default=b"", repr=False)
    """Serialized aecp.common.v1.OwnershipBoundary, captured verbatim from
    SpawnSessionRequest so a handoff-spawned session never re-derives it."""
    task_node_snapshot: bytes = field(default=b"", repr=False)
    """Opaque, Coordinator-forwarded serialization of taskgraph.v1.TaskNode."""
    spawned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LifecycleManager:
    def __init__(
        self,
        sandbox,
        identity_issuer,
        session_ttl_seconds: int,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.sandbox = sandbox
        self.identity_issuer = identity_issuer
        self.session_ttl_seconds = session_ttl_seconds
        self._now = now_fn
        self._lock = asyncio.Lock()
        self._sessions: dict[str, AgentSession] = {}
        self._sandbox_handles: dict[str, object] = {}

    async def spawn(
        self,
        tenant_id: str,
        task_id: str,
        granted_risk_tier: str,
        ownership_globs: list[str],
        ownership_boundary: bytes,
        task_node_snapshot: bytes,
    ) -> AgentSession:
        """Create a new sandboxed agent session scoped to exactly one task
        node and its ownership boundary.
        """
        session_id = str(uuid4())
        now = self._now()

        handle = await self.sandbox.create(session_id, tenant_id, ownership_globs)
        await self.identity_issuer.issue(session_id, self.session_ttl_seconds)

        session = AgentSession(
            session_id=session_id,
            tenant_id=tenant_id,
            task_id=task_id,
            status="ACTIVE",
            granted_risk_tier=granted_risk_tier,
            ownership_boundary=ownership_boundary,
            task_node_snapshot=task_node_snapshot,
            spawned_at=now,
            expires_at=now + timedelta(seconds=self.session_ttl_seconds),
        )

        async with self._lock:
            self._sessions[session_id] = session
            self._sandbox_handles[session_id] = handle

        return session

    async def get(self, session_id: str) -> AgentSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def count_active(self, tenant_id: str) -> int:
        async with self._lock:
            return sum(
                1 for s in self._sessions.values() if s.tenant_id == tenant_id
            )

    async def terminate(self, session_id: str, reason: str) -> None:
        """Tear down a session's sandbox and revoke its scoped credentials."""
        await self.terminate_and_return(session_id, reason)

    async def terminate_and_return(self, session_id: str, reason: str) -> AgentSession | None:
        """Atomically claim and terminate a session, returning it (or None
        if it was already gone).

        This is the atomic primitive terminate(), reap_expired(), and
        HandoffCoordinator.handoff() all build on: the pop from
        self._sessions happens under self._lock in a single step, so two
        concurrent callers racing to terminate/hand off the *same*
        session_id can never both observe it as present — exactly one
        gets the AgentSession back, the other gets None. Without this,
        "get() then terminate()" would be a check-then-act race where both
        callers could see the session as live and both proceed (see
        tests/test_concurrent_sessions.py).
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            handle = self._sandbox_handles.pop(session_id, None)

        if session is None:
            return None

        if handle is not None:
            await self.sandbox.destroy(handle)
        await self.identity_issuer.revoke(session_id)
        return session

    async def reap_expired(self) -> list[AgentSession]:
        """Find and terminate sessions past their TTL; return the sessions
        (not just ids) so the caller can notify the Coordinator to
        re-schedule their tasks — that notification needs task_id/
        tenant_id, which a bare id list would lose.
        """
        now = self._now()

        async with self._lock:
            expired_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.expires_at <= now
            ]

        expired: list[AgentSession] = []
        for session_id in expired_ids:
            session = await self.terminate_and_return(session_id, reason="ttl_expired")
            if session is not None:
                expired.append(session)

        return expired
