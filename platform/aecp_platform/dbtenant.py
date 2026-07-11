"""Tenant isolation for every Postgres query issued by any AECP service.

AECP is a multi-tenant SaaS: one tenant's task graph, decision log, or
agent output must never be readable by another tenant, even under an
application bug. Isolation is enforced at two layers:

1. Every tenant-scoped table carries a NOT NULL tenant_id column with a
   Postgres Row-Level Security policy (see */migrations).
2. Every connection this module hands out sets the RLS session variable
   from a server-derived tenant context — never from a client-supplied
   field — so RLS is actually active for the transaction's lifetime.

A query issued without a tenant bound to context must fail closed.
"""

from __future__ import annotations

import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import NewType

TenantID = NewType("TenantID", str)

_current_tenant: contextvars.ContextVar[TenantID] = contextvars.ContextVar("aecp_tenant")


def bind_tenant(tenant: TenantID) -> contextvars.Token:
    """Bind a tenant to the current context for the remainder of a request."""
    raise NotImplementedError


def current_tenant() -> TenantID:
    """Return the tenant bound to the current context.

    Raises if none is set — there is deliberately no default tenant.
    """
    raise NotImplementedError


class TenantScopedPool:
    """Wraps an asyncpg pool and only ever hands out connections that have
    had `SELECT set_config('app.tenant_id', ...)` applied inside an open
    transaction, so every RLS policy in the schema is enforced
    automatically without each call site remembering to scope its
    WHERE clause.
    """

    def __init__(self, pool) -> None:
        raise NotImplementedError

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[object]:
        """Open a transaction scoped to the tenant bound in context.

        Raises if no tenant is bound. Uses `SET LOCAL` semantics (via
        set_config(..., is_local=true)) so the RLS context cannot leak
        across pooled-connection reuse.
        """
        raise NotImplementedError
        yield  # pragma: no cover - placeholder to keep this a generator
