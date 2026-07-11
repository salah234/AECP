"""Tenant-scoped persistence for decision log entries, ownership records,
interface contracts, and drift reports.

All reads/writes go through aecp_platform.dbtenant.TenantScopedPool so
Row-Level Security is applied automatically. Large context artifacts
(hydration bundles, agent transcripts) are stored in object storage, not
Postgres — this repository only stores their URIs.
"""

from __future__ import annotations


class StateRepository:
    def __init__(self, pool, object_storage_client) -> None:
        raise NotImplementedError

    async def insert_decision(self, entry) -> None:
        raise NotImplementedError

    async def upsert_ownership(self, record) -> None:
        raise NotImplementedError

    async def get_contract(self, contract_id: str):
        raise NotImplementedError

    async def insert_drift_report(self, report) -> None:
        raise NotImplementedError

    async def put_artifact(self, tenant_id: str, key: str, data: bytes) -> str:
        """Store a large context artifact in object storage and return its URI."""
        raise NotImplementedError

    async def get_artifact(self, uri: str) -> bytes:
        raise NotImplementedError
