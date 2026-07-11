"""Provider-agnostic secret access.

Services depend only on the `SecretProvider` protocol, never on a concrete
backend, so swapping an env-based provider (local dev) for a KMS/Vault
backed provider (production) is a wiring change, not a code change.

No secret value should ever be logged.
"""

from __future__ import annotations

from typing import Protocol


class SecretValue:
    """Wraps secret material so it is never accidentally logged.

    __repr__/__str__ must be redacted; the raw value is only reachable via
    `expose()`.
    """

    def __init__(self, raw: str) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        raise NotImplementedError

    def expose(self) -> str:
        """Return the underlying secret material. Hold the result for the
        shortest possible scope; never pass it to a logger or trace.
        """
        raise NotImplementedError


class SecretProvider(Protocol):
    """Resolves a named secret to its current value."""

    async def get(self, key: str) -> SecretValue: ...


class EnvSecretProvider:
    """Reads secrets from environment variables.

    Local development and CI only — production deployments must use a
    KMS/Vault backed provider (see docs/adr/0006-secrets-management.md).
    """

    def __init__(self, prefix: str = "") -> None:
        raise NotImplementedError

    async def get(self, key: str) -> SecretValue:
        raise NotImplementedError


class KMSSecretProvider:
    """Placeholder for a cloud KMS/Vault-backed provider.

    Wiring a real backend (AWS Secrets Manager, GCP Secret Manager,
    HashiCorp Vault) is tracked in docs/adr/0006-secrets-management.md.
    """

    async def get(self, key: str) -> SecretValue:
        raise NotImplementedError
