"""Shared error taxonomy.

A small closed set of exception types lets the gateway map errors to HTTP
status codes and lets the audit layer decide what must be written to the
immutable audit trail, without parsing error strings.
"""

from __future__ import annotations


class AECPError(Exception):
    """Base class for all AECP application errors."""


class NotFoundError(AECPError):
    """Requested resource does not exist."""


class AlreadyExistsError(AECPError):
    """Resource already exists (idempotency / uniqueness conflict)."""


class InvalidArgumentError(AECPError):
    """Caller-supplied input failed validation."""


class PermissionDeniedError(AECPError):
    """Caller is authenticated but not authorized for this action."""


class UnauthenticatedError(AECPError):
    """Caller could not be authenticated."""


class FailedPreconditionError(AECPError):
    """Operation is not valid given current system state."""


class RiskTierExceededError(AECPError):
    """Raised when an agent or task attempts to act at a higher risk tier
    than the task graph granted it.

    """


class OwnershipViolationError(AECPError):
    """Raised when a change touches files/modules outside a task node's
    declared ownership boundary.
    """


def is_security_relevant(err: Exception) -> bool:
    """Return whether ``err`` must be written to the immutable audit log.

    Security-relevant errors: auth/authz failures, risk-tier escalation
    attempts, and ownership boundary violations.
    """
    raise NotImplementedError
