"""Per-task scoped credential issuance for agent sessions.

Agent workers never hold a static, long-lived API key. Each session
receives a short-lived, narrowly-scoped credential (mTLS client cert or
signed token) valid only for the duration of its TTL and only for calling
the specific services it needs — Coordinator and State, per
deploy/k8s/networkpolicy/agents-edges.yaml and
docs/adr/0007-agent-pool-has-no-taskgraph-edge.md — never other agent
sessions, per CLAUDE.md's no-agent-to-agent invariant.

This issues an HMAC-signed opaque token, not a real mTLS client
certificate: platform/aecp_platform/identity.py (SPIFFE-style workload
identity, MTLSConfig) is a Tier 3 security boundary owned by /platform
and is not yet implemented (see CLAUDE.md Escalation Policy). This class
is the interim scheme until that lands; it is deliberately self-contained
(stdlib hmac only) so it does not depend on the unimplemented platform
module.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# The only two internal services an agent session's credential may ever
# be scoped to. Matches agents-edges.yaml's egress allow-list exactly.
ALLOWED_SERVICE_IDENTITIES: tuple[str, ...] = ("coordinator", "state")


@dataclass
class ScopedCredential:
    session_id: str
    expires_at: str
    allowed_service_identities: list[str]
    token: str = field(default="", repr=False)
    """Opaque bearer value. Excluded from repr/logs by convention, mirroring
    aecp_platform.secrets.SecretValue's no-unredacted-repr design even
    though this class predates that module being usable."""


class CredentialIssuer:
    """Issues and revokes ScopedCredentials backed by an HMAC signature.

    A credential's token is `session_id|expires_at|signature` (pipe-
    delimited: an ISO timestamp's fractional seconds contain a literal
    ".", so "." can't be the delimiter), where signature =
    HMAC-SHA256(signing_key, f"{session_id}|{expires_at}").
    Verifying a token requires knowing signing_key, so possession of a
    valid token proves it was issued by this (or a key-sharing) issuer,
    without needing a database round-trip to check validity — except for
    revocation, which is tracked in-memory here since sessions are
    disposable/short-lived by design (no durable revocation list needed
    across a process restart; a restart already invalidates every
    in-flight session per lifecycle.py's in-memory registry).
    """

    def __init__(self, signing_key: bytes) -> None:
        if not signing_key:
            raise ValueError("signing_key must not be empty")
        self._signing_key = signing_key
        self._revoked: set[str] = set()
        self._issued: dict[str, ScopedCredential] = {}

    async def issue(self, session_id: str, ttl_seconds: int) -> ScopedCredential:
        """Issue a short-lived credential scoped to exactly this session's
        allowed service calls.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        self._revoked.discard(session_id)

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat()
        token = self._sign(session_id, expires_at)

        credential = ScopedCredential(
            session_id=session_id,
            expires_at=expires_at,
            allowed_service_identities=list(ALLOWED_SERVICE_IDENTITIES),
            token=token,
        )
        self._issued[session_id] = credential
        return credential

    async def revoke(self, session_id: str) -> None:
        """Revoke a session's credential immediately (e.g. on
        termination or handoff), rather than waiting for TTL expiry.
        """
        self._revoked.add(session_id)
        self._issued.pop(session_id, None)

    def verify(self, token: str) -> str | None:
        """Return the session_id encoded in `token` if it is a
        well-formed, correctly-signed, unexpired, unrevoked credential;
        otherwise None.

        Verification is done by recomputing the HMAC signature, not by
        looking up self._issued — the point of signing is that any holder
        of signing_key can verify a token without sharing the issuer's
        in-memory state. Revocation is instance-local (an acknowledged MVP
        limitation, acceptable because sessions are already disposable and
        in-memory; see class docstring).
        """
        try:
            session_id, expires_at, signature = token.split("|", 2)
        except ValueError:
            return None

        expected_signature = hmac.new(
            self._signing_key,
            f"{session_id}|{expires_at}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        if session_id in self._revoked:
            return None

        try:
            expires_at_dt = datetime.fromisoformat(expires_at)
        except ValueError:
            return None

        if datetime.now(timezone.utc) >= expires_at_dt:
            return None

        return session_id

    def _sign(self, session_id: str, expires_at: str) -> str:
        signature = hmac.new(
            self._signing_key,
            f"{session_id}|{expires_at}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{session_id}|{expires_at}|{signature}"


def generate_signing_key() -> bytes:
    """Generate a fresh random signing key (dev/test convenience)."""
    return secrets.token_bytes(32)
