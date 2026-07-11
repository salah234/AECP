"""Tenant context resolution for gateway requests.

The tenant bound to a request must always be derived from the verified
session (auth.Session.tenant_id), never from a client-supplied header,
query param, or body field. This module is the single place that
performs that derivation and attaches it to outgoing internal gRPC calls.
"""

from __future__ import annotations


def tenant_from_session(session) -> str:
    """Return the tenant id to scope this request to. Raises if the
    session has no associated tenant.
    """
    raise NotImplementedError


def attach_tenant_metadata(grpc_call_metadata: list, tenant_id: str) -> list:
    """Append the tenant context to outgoing gRPC call metadata so
    downstream services can bind it via aecp_platform.dbtenant.
    """
    raise NotImplementedError
