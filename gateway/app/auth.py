"""OIDC authentication for human users (EMs, reviewers).

AECP never stores passwords or long-lived credentials for human users.
Login delegates to a pluggable external OIDC provider (Auth0/WorkOS/Okta/
generic OIDC); this module only handles the authorization-code exchange,
session issuance, and verification of the resulting session on each
request. Agent/service auth is handled separately by
aecp_platform.identity (mTLS), never by this module.

issue_session_cookie/verify_session_cookie take the signing key as an
explicit parameter rather than reading it from module-level state: it's a
pure function this way (easy to test without touching global config) and
avoids CLAUDE.md's preference for explicit, boring data flow over hidden
state.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from aecp_platform.errors import UnauthenticatedError

_OIDC_SCOPE = "openid profile email"
_SESSION_COOKIE_SALT = "aecp-gateway-session"


@dataclass
class Session:
    subject: str
    tenant_id: str
    role: str
    expires_at: str


class OIDCClient:
    def __init__(self, issuer_url: str, client_id: str, client_secret: str, redirect_url: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_url = redirect_url

        # Discovery is a one-time synchronous call made at startup
        # (OIDCClient is constructed once in main.py, not per-request), so
        # every route handler can treat authorization_redirect_url as a
        # cheap, synchronous string-builder rather than an async call.
        discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        with httpx.Client(timeout=10.0) as client:
            metadata = client.get(discovery_url)
            metadata.raise_for_status()
            metadata_json = metadata.json()

            jwks = client.get(metadata_json["jwks_uri"])
            jwks.raise_for_status()
            self._jwks = KeySet.import_key_set(jwks.json())

        self._issuer = metadata_json["issuer"]
        self._authorization_endpoint = metadata_json["authorization_endpoint"]
        self._token_endpoint = metadata_json["token_endpoint"]

    def authorization_redirect_url(self, state: str) -> str:
        """Build the URL to redirect the browser to for login."""
        params = httpx.QueryParams(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_url,
                "scope": _OIDC_SCOPE,
                "state": state,
            }
        )
        return f"{self._authorization_endpoint}?{params}"

    async def exchange_code(self, code: str, state: str) -> Session:
        """Exchange an authorization code for tokens, verify the ID token,
        and resolve the caller's tenant + role (via claims or a follow-up
        lookup against the State Layer).
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                self._token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_url,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        if token_response.status_code != httpx.codes.OK:
            raise UnauthenticatedError(
                f"OIDC token exchange failed: {token_response.status_code}"
            )

        id_token = token_response.json().get("id_token")
        if not id_token:
            raise UnauthenticatedError("OIDC token response carried no id_token")

        registry = JWTClaimsRegistry(
            iss={"essential": True, "value": self._issuer},
            aud={"essential": True, "value": self._client_id},
            exp={"essential": True},
        )
        try:
            token = jwt.decode(id_token, self._jwks)
            registry.validate(token.claims)
        except JoseError as exc:
            raise UnauthenticatedError(f"ID token failed verification: {exc}") from exc

        claims = token.claims
        subject = claims.get("sub")
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")
        if not subject or not tenant_id or not role:
            # A follow-up lookup against the State Layer for tenant/role
            # (when the IdP doesn't carry custom claims) is real future
            # work, not something to fake here with a placeholder tenant.
            raise UnauthenticatedError(
                "ID token is missing required subject/tenant_id/role claims"
            )

        return Session(
            subject=subject,
            tenant_id=tenant_id,
            role=role,
            expires_at=_iso(claims.get("exp")),
        )


def _iso(exp: float | int | None) -> str:
    if exp is None:
        raise UnauthenticatedError("ID token is missing an exp claim")
    return datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat()


def issue_session_cookie(session: Session, secret_key: str) -> str:
    """Sign and serialize a session into a cookie value."""
    serializer = URLSafeTimedSerializer(secret_key, salt=_SESSION_COOKIE_SALT)
    return serializer.dumps(asdict(session))


def verify_session_cookie(cookie_value: str, secret_key: str, max_age_seconds: int = 3600) -> Session:
    """Verify signature and expiry, returning the Session or raising
    UnauthenticatedError.
    """
    serializer = URLSafeTimedSerializer(secret_key, salt=_SESSION_COOKIE_SALT)
    try:
        payload = serializer.loads(cookie_value, max_age=max_age_seconds)
    except SignatureExpired as exc:
        raise UnauthenticatedError("Session cookie has expired") from exc
    except BadSignature as exc:
        raise UnauthenticatedError("Session cookie failed signature verification") from exc

    try:
        return Session(**payload)
    except TypeError as exc:
        raise UnauthenticatedError("Session cookie payload is malformed") from exc
