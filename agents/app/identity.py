"""Per-task scoped credential issuance for agent sessions.

Agent workers never hold a static, long-lived API key. Each session
receives a short-lived, narrowly-scoped credential (mTLS client cert or
signed token) valid only for the duration of its TTL and only for calling
the specific services (Coordinator, State, TaskGraph) it needs — never
other agent sessions, per CLAUDE.md's no-agent-to-agent invariant.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScopedCredential:
    session_id: str
    expires_at: str
    allowed_service_identities: list[str]


class CredentialIssuer:
    def __init__(self, ca_signer) -> None:
        raise NotImplementedError

    async def issue(self, session_id: str, ttl_seconds: int) -> ScopedCredential:
        """Issue a short-lived credential scoped to exactly this session's
        allowed service calls.
        """
        raise NotImplementedError

    async def revoke(self, session_id: str) -> None:
        """Revoke a session's credential immediately (e.g. on
        termination or handoff), rather than waiting for TTL expiry.
        """
        raise NotImplementedError
