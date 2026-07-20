"""Tests for app.auth: session cookie signing and the OIDC exchange flow.

The OIDC flow is exercised end to end against a fake IdP (discovery +
JWKS + token endpoint responses monkeypatched onto httpx), signing a real
ID token with joserfc so verification logic runs for real rather than
being mocked away.
"""

from __future__ import annotations

import time

import pytest
from joserfc import jwk
from joserfc import jwt as joserfc_jwt

from aecp_platform.errors import UnauthenticatedError
from app.auth import Session, issue_session_cookie, verify_session_cookie

SECRET_KEY = "unit-test-secret"


def test_session_cookie_round_trip():
    session = Session(subject="user-1", tenant_id="tenant-a", role="em", expires_at="2099-01-01T00:00:00+00:00")

    cookie = issue_session_cookie(session, SECRET_KEY)
    recovered = verify_session_cookie(cookie, SECRET_KEY)

    assert recovered == session


def test_verify_session_cookie_rejects_bad_signature():
    session = Session(subject="user-1", tenant_id="tenant-a", role="em", expires_at="2099-01-01T00:00:00+00:00")
    cookie = issue_session_cookie(session, SECRET_KEY)

    with pytest.raises(UnauthenticatedError):
        verify_session_cookie(cookie, "a-different-secret")


def test_verify_session_cookie_rejects_expired_cookie():
    session = Session(subject="user-1", tenant_id="tenant-a", role="em", expires_at="2099-01-01T00:00:00+00:00")
    cookie = issue_session_cookie(session, SECRET_KEY)

    with pytest.raises(UnauthenticatedError):
        verify_session_cookie(cookie, SECRET_KEY, max_age_seconds=-1)


def test_verify_session_cookie_rejects_malformed_payload():
    from itsdangerous import URLSafeTimedSerializer

    from app.auth import _SESSION_COOKIE_SALT

    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=_SESSION_COOKIE_SALT)
    cookie = serializer.dumps({"unexpected": "shape"})

    with pytest.raises(UnauthenticatedError):
        verify_session_cookie(cookie, SECRET_KEY)


class _FakeHTTPResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def rsa_key():
    return jwk.RSAKey.generate_key(2048, private=True)


@pytest.fixture
def oidc_client(monkeypatch, rsa_key):
    """Builds a real OIDCClient against a fully faked IdP: discovery,
    JWKS, and (for exchange_code tests) a token endpoint response, all
    served via a monkeypatched httpx.
    """
    issuer = "https://idp.example.test"
    jwks_public = jwk.KeySet([rsa_key]).as_dict(private=False)

    discovery = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
    }

    def fake_get(self, url, *args, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return _FakeHTTPResponse(discovery)
        if url.endswith("/jwks"):
            return _FakeHTTPResponse(jwks_public)
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr("httpx.Client.get", fake_get)

    from app.auth import OIDCClient

    return OIDCClient(issuer, "gateway", "client-secret", "https://gateway.example.test/auth/callback")


def test_authorization_redirect_url_contains_client_and_state(oidc_client):
    url = oidc_client.authorization_redirect_url("csrf-state-value")

    assert url.startswith("https://idp.example.test/authorize?")
    assert "client_id=gateway" in url
    assert "state=csrf-state-value" in url
    assert "response_type=code" in url


def _sign_id_token(rsa_key, *, issuer, audience, extra_claims=None, exp_delta=3600):
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": "user-1",
        "exp": int(time.time()) + exp_delta,
        "iat": int(time.time()),
        **(extra_claims or {}),
    }
    header = {"alg": "RS256", "kid": rsa_key.kid}
    return joserfc_jwt.encode(header, claims, rsa_key)


@pytest.mark.asyncio
async def test_exchange_code_resolves_session_from_id_token_claims(monkeypatch, oidc_client, rsa_key):
    id_token = _sign_id_token(
        rsa_key,
        issuer="https://idp.example.test",
        audience="gateway",
        extra_claims={"tenant_id": "tenant-a", "role": "em"},
    )

    async def fake_post(self, url, *args, **kwargs):
        assert url == "https://idp.example.test/token"
        return _FakeHTTPResponse({"id_token": id_token, "access_token": "unused"})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    session = await oidc_client.exchange_code("auth-code", "state-value")

    assert session.subject == "user-1"
    assert session.tenant_id == "tenant-a"
    assert session.role == "em"


@pytest.mark.asyncio
async def test_exchange_code_rejects_id_token_missing_tenant_claim(monkeypatch, oidc_client, rsa_key):
    id_token = _sign_id_token(
        rsa_key, issuer="https://idp.example.test", audience="gateway", extra_claims={"role": "em"}
    )

    async def fake_post(self, url, *args, **kwargs):
        return _FakeHTTPResponse({"id_token": id_token})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(UnauthenticatedError):
        await oidc_client.exchange_code("auth-code", "state-value")


@pytest.mark.asyncio
async def test_exchange_code_rejects_wrong_audience(monkeypatch, oidc_client, rsa_key):
    id_token = _sign_id_token(
        rsa_key,
        issuer="https://idp.example.test",
        audience="some-other-client",
        extra_claims={"tenant_id": "tenant-a", "role": "em"},
    )

    async def fake_post(self, url, *args, **kwargs):
        return _FakeHTTPResponse({"id_token": id_token})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(UnauthenticatedError):
        await oidc_client.exchange_code("auth-code", "state-value")


@pytest.mark.asyncio
async def test_exchange_code_rejects_expired_id_token(monkeypatch, oidc_client, rsa_key):
    id_token = _sign_id_token(
        rsa_key,
        issuer="https://idp.example.test",
        audience="gateway",
        extra_claims={"tenant_id": "tenant-a", "role": "em"},
        exp_delta=-3600,
    )

    async def fake_post(self, url, *args, **kwargs):
        return _FakeHTTPResponse({"id_token": id_token})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(UnauthenticatedError):
        await oidc_client.exchange_code("auth-code", "state-value")
