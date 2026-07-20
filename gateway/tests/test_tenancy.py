from __future__ import annotations

from dataclasses import dataclass

import pytest

from aecp_platform.errors import UnauthenticatedError
from app.tenancy import TENANT_METADATA_KEY, attach_tenant_metadata, tenant_from_session


@dataclass
class _FakeSession:
    tenant_id: str | None


def test_tenant_from_session_returns_tenant_id():
    assert tenant_from_session(_FakeSession(tenant_id="tenant-a")) == "tenant-a"


def test_tenant_from_session_rejects_missing_tenant():
    with pytest.raises(UnauthenticatedError):
        tenant_from_session(_FakeSession(tenant_id=None))


def test_tenant_from_session_rejects_empty_tenant():
    with pytest.raises(UnauthenticatedError):
        tenant_from_session(_FakeSession(tenant_id=""))


def test_attach_tenant_metadata_appends_without_mutating_input():
    original = [("caller-id", "gateway")]

    result = attach_tenant_metadata(original, "tenant-a")

    assert original == [("caller-id", "gateway")]
    assert result == [("caller-id", "gateway"), (TENANT_METADATA_KEY, "tenant-a")]
