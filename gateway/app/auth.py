"""OIDC authentication for human users (EMs, reviewers).

AECP never stores passwords or long-lived credentials for human users.
Login delegates to a pluggable external OIDC provider (Auth0/WorkOS/Okta/
generic OIDC); this module only handles the authorization-code exchange,
session issuance, and verification of the resulting session on each
request. Agent/service auth is handled separately by
aecp_platform.identity (mTLS), never by this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Session:
    subject: str
    tenant_id: str
    role: str
    expires_at: str


class OIDCClient:
    def __init__(self, issuer_url: str, client_id: str, client_secret: str, redirect_url: str) -> None:
        raise NotImplementedError

    def authorization_redirect_url(self, state: str) -> str:
        """Build the URL to redirect the browser to for login."""
        raise NotImplementedError

    async def exchange_code(self, code: str, state: str) -> Session:
        """Exchange an authorization code for tokens, verify the ID token,
        and resolve the caller's tenant + role (via claims or a follow-up
        lookup against the State Layer).
        """
        raise NotImplementedError


def issue_session_cookie(session: Session) -> str:
    """Sign and serialize a session into a cookie value."""
    raise NotImplementedError


def verify_session_cookie(cookie_value: str) -> Session:
    """Verify signature and expiry, returning the Session or raising
    UnauthenticatedError.
    """
    raise NotImplementedError
