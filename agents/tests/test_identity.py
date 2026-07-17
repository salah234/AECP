"""Tests for CredentialIssuer's HMAC-signed token scheme."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.identity import ALLOWED_SERVICE_IDENTITIES, CredentialIssuer, generate_signing_key


def make_issuer() -> CredentialIssuer:
    return CredentialIssuer(signing_key=generate_signing_key())


async def test_issue_returns_credential_scoped_to_coordinator_and_state() -> None:
    issuer = make_issuer()

    credential = await issuer.issue("session-1", ttl_seconds=60)

    assert credential.session_id == "session-1"
    assert credential.allowed_service_identities == list(ALLOWED_SERVICE_IDENTITIES)
    assert credential.token
    assert issuer.verify(credential.token) == "session-1"


async def test_verify_rejects_malformed_or_tampered_token() -> None:
    issuer = make_issuer()
    credential = await issuer.issue("session-1", ttl_seconds=60)

    assert issuer.verify("not-a-real-token") is None
    assert issuer.verify(credential.token + "tampered") is None


async def test_verify_rejects_expired_token() -> None:
    issuer = make_issuer()

    # issue() rejects ttl_seconds <= 0 outright, so build an
    # already-expired token directly via _sign to exercise the expiry
    # check in verify() specifically.
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    expired_token = issuer._sign("session-1", past)

    assert issuer.verify(expired_token) is None


async def test_revoke_immediately_invalidates_credential() -> None:
    issuer = make_issuer()
    credential = await issuer.issue("session-1", ttl_seconds=3600)

    await issuer.revoke("session-1")

    assert issuer.verify(credential.token) is None


async def test_second_issuer_with_same_signing_key_can_verify_the_token() -> None:
    """Proves the scheme is genuinely stateless-verifiable: anyone holding
    signing_key can verify, not just the instance that issued it.
    """
    signing_key = generate_signing_key()
    issuer_a = CredentialIssuer(signing_key=signing_key)
    issuer_b = CredentialIssuer(signing_key=signing_key)

    credential = await issuer_a.issue("session-1", ttl_seconds=60)

    assert issuer_b.verify(credential.token) == "session-1"


async def test_issuer_with_different_signing_key_rejects_the_token() -> None:
    issuer_a = CredentialIssuer(signing_key=generate_signing_key())
    issuer_b = CredentialIssuer(signing_key=generate_signing_key())

    credential = await issuer_a.issue("session-1", ttl_seconds=60)

    assert issuer_b.verify(credential.token) is None
