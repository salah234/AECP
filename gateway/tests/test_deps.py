"""Exercises app.deps.get_request_context through a real protected route
(/api/v1/me) rather than calling the dependency function directly, so the
FastAPI wiring (cookie reading, exception handling, status codes) is
covered too.
"""

from __future__ import annotations

from app.deps import SESSION_COOKIE_NAME
from app.main import app as fastapi_app
from app.rate_limit import RateLimiter


def test_me_requires_a_session_cookie(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_me_rejects_an_invalid_session_cookie(client):
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-signed-cookie")

    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_me_returns_session_identity_for_a_valid_cookie(authed_client):
    response = authed_client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "user-1"
    assert body["role"] == "em"
    assert body["tenantId"]


def test_auth_failure_is_written_to_the_audit_trail(client, fake_clients):
    client.get("/api/v1/me")

    fake_clients._observability.RecordAuditEvent.assert_awaited_once()
    call_args = fake_clients._observability.RecordAuditEvent.call_args
    request = call_args.args[0]
    assert request.event.action == "auth_failure"
    assert request.event.security_relevant is True


def test_rate_limit_exceeded_returns_429(authed_client):
    # Swap in a one-request-per-minute limiter after the fixture already
    # wired a permissive one, to exercise the 429 path deterministically.
    fastapi_app.state.rate_limiter = RateLimiter(requests_per_minute=1)

    first = authed_client.get("/api/v1/me")
    second = authed_client.get("/api/v1/me")

    assert first.status_code == 200
    assert second.status_code == 429
