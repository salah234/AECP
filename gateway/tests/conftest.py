"""Shared fixtures for gateway's fast unit suite.

Every test here runs against fakes (no real network, no real IdP, no
real internal services) — mirrors coordinator/tests/fakes.py's approach
of exercising real domain logic (app.deps, app.routers.*, app.auth,
app.tenancy) against in-memory test doubles rather than a live topology.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import SESSION_COOKIE_NAME
from app.main import app
from app.rate_limit import RateLimiter

TEST_SECRET_KEY = "unit-test-session-secret"
TEST_TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        http_port=8080,
        session_secret_key=TEST_SECRET_KEY,
        oidc_issuer_url="https://idp.example.test",
        oidc_client_id="gateway",
        oidc_client_secret_key="unit-test-client-secret",
        oidc_redirect_url="https://gateway.example.test/auth/callback",
        coordinator_addr="coordinator:50054",
        taskgraph_addr="taskgraph:50052",
        state_addr="state:50051",
        integration_addr="integration:50055",
        observability_addr="observability:50056",
        rate_limit_requests_per_minute=1000,
        otel_collector_endpoint="otel-collector:4317",
        mtls_cert_file="",
        mtls_key_file="",
        mtls_ca_file="",
    )


class FakeStub:
    """A stand-in for a generated *Stub class: tests set whichever RPC
    method they need as an AsyncMock, e.g. stub.GetTaskNode = AsyncMock(...).
    """


class FakeInternalServiceClients:
    """Stands in for app.proxy.InternalServiceClients: same public
    surface (coordinator()/taskgraph()/state()/integration()/
    observability()/metadata()), backed by FakeStub()s instead of real
    gRPC channels.
    """

    def __init__(self) -> None:
        self._coordinator = FakeStub()
        self._taskgraph = FakeStub()
        self._state = FakeStub()
        self._integration = FakeStub()
        self._observability = FakeStub()
        self._observability.RecordAuditEvent = AsyncMock()

    def coordinator(self):
        return self._coordinator

    def taskgraph(self):
        return self._taskgraph

    def state(self):
        return self._state

    def integration(self):
        return self._integration

    def observability(self):
        return self._observability

    def metadata(self, tenant_id: str) -> list[tuple[str, str]]:
        return [("caller-id", "gateway"), ("tenant-id", tenant_id)]


@pytest.fixture
def fake_clients() -> FakeInternalServiceClients:
    return FakeInternalServiceClients()


@pytest.fixture
def client(settings, fake_clients) -> TestClient:
    """A TestClient wired to fakes, bypassing main.py's real lifespan
    (which would call Settings.from_env() / build real gRPC channels /
    do a real OIDC discovery HTTP call).
    """
    app.state.settings = settings
    app.state.clients = fake_clients
    app.state.rate_limiter = RateLimiter(settings.rate_limit_requests_per_minute)
    app.state.oidc_client = None
    return TestClient(app)


@pytest.fixture
def session_cookie(settings) -> str:
    from app.auth import Session, issue_session_cookie

    session = Session(
        subject="user-1", tenant_id=TEST_TENANT_ID, role="em", expires_at="2099-01-01T00:00:00+00:00"
    )
    return issue_session_cookie(session, settings.session_secret_key)


@pytest.fixture
def authed_client(client, session_cookie) -> TestClient:
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie)
    return client
