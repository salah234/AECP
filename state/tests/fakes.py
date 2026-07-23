"""In-memory test doubles for state-layer components.

Used to exercise DecisionLog, OwnershipMap, ContractRegistry, DriftDetector,
and StateServicer end-to-end against real domain logic without a live
Postgres connection or mTLS server. Mirrors taskgraph/tests/fakes.py's
style and the AbortedRPC/FakeContext pattern in particular, so gRPC
not-found paths (which rely on context.abort() actually terminating the
RPC, as grpc.aio's real abort() does) can be exercised the same way here.
"""

from __future__ import annotations

from app.contracts import InterfaceContract
from app.decision_log import DecisionLogEntry
from app.drift import DriftReport, ModuleState
from app.ownership_map import OwnershipRecord


class AbortedRPC(Exception):
    """Raised by FakeContext.abort to mimic grpc.aio's abort-terminates-the-RPC
    semantics, so tests can assert on the status code that would have been
    sent to the caller.
    """

    def __init__(self, code, details: str = "") -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    async def abort(self, code, details: str = "") -> None:
        raise AbortedRPC(code, details)


class FakeStateRepository:
    """Implements the subset of StateRepository's async interface that
    DecisionLog, OwnershipMap, ContractRegistry, and DriftDetector depend
    on, backed by plain dicts/lists.

    Contract storage is keyed by (contract_id, version) to mirror the real
    table's composite primary key and ON CONFLICT (contract_id, version)
    upsert semantics in repository.save_contract.
    """

    def __init__(self) -> None:
        self.decisions: list[DecisionLogEntry] = []
        self.ownership: dict[tuple[str, str], OwnershipRecord] = {}
        self.contracts: dict[tuple[str, int], InterfaceContract] = {}
        self.drift_reports: dict[str, DriftReport] = {}
        self.module_states: dict[tuple[str, str], ModuleState] = {}

    # -- decision log -----------------------------------------------------

    async def insert_decision(self, entry: DecisionLogEntry) -> None:
        self.decisions.append(entry)

    async def get_decisions_by_task(self, task_id: str) -> list[DecisionLogEntry]:
        return [
            entry
            for entry in sorted(self.decisions, key=lambda e: e.decided_at)
            if entry.task_id == task_id
        ]

    async def get_decisions_for_module(
        self,
        tenant_id: str,
        module_path: str,
    ) -> list[DecisionLogEntry]:
        ownership_record = await self.get_ownership(tenant_id, module_path)
        if ownership_record is None:
            return []

        return await self.get_decisions_by_task(ownership_record.last_task_id)

    async def get_recent_decisions(self, limit: int) -> list[DecisionLogEntry]:
        return sorted(self.decisions, key=lambda e: e.decided_at, reverse=True)[:limit]

    # -- ownership ----------------------------------------------------------

    async def upsert_ownership(self, record: OwnershipRecord) -> None:
        self.ownership[(record.tenant_id, record.module_path)] = record

    async def get_ownership(
        self,
        tenant_id: str,
        module_path: str,
    ) -> OwnershipRecord | None:
        return self.ownership.get((tenant_id, module_path))

    # -- contracts ------------------------------------------------------

    async def get_contract(self, contract_id: str) -> InterfaceContract | None:
        versions = [
            contract
            for (cid, _version), contract in self.contracts.items()
            if cid == contract_id
        ]
        if not versions:
            return None

        return max(versions, key=lambda c: c.version)

    async def get_contract_version(
        self,
        contract_id: str,
        version: int,
    ) -> InterfaceContract | None:
        return self.contracts.get((contract_id, version))

    async def save_contract(self, contract: InterfaceContract) -> None:
        self.contracts[(contract.contract_id, contract.version)] = contract

    # -- drift ------------------------------------------------------------

    async def insert_drift_report(self, report: DriftReport) -> None:
        self.drift_reports[report.report_id] = report

    async def get_drift_report(self, report_id: str) -> DriftReport | None:
        return self.drift_reports.get(report_id)

    async def update_drift_report(self, report: DriftReport) -> None:
        self.drift_reports[report.report_id] = report

    async def get_module_state(
        self,
        tenant_id: str,
        module_path: str,
    ) -> ModuleState | None:
        return self.module_states.get((tenant_id, module_path))

    async def save_module_state(self, state: ModuleState) -> None:
        self.module_states[(state.tenant_id, state.module_path)] = state

    # -- artifacts ----------------------------------------------------------

    async def put_artifact(self, tenant_id: str, key: str, data: bytes) -> str:
        raise NotImplementedError("use a real/fake ObjectStorageClient for artifact tests")

    async def get_artifact(self, uri: str) -> bytes:
        raise NotImplementedError("use a real/fake ObjectStorageClient for artifact tests")


class FakeObjectStorageClient:
    """In-memory stand-in for aecp_platform.storage.ObjectStorageClient,
    matching its async put/get surface without touching the filesystem.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, tenant_id: str | None = None) -> str:
        storage_key = f"{tenant_id}/{key}" if tenant_id else key
        self._objects[storage_key] = data
        return storage_key

    async def get(self, key: str) -> bytes:
        return self._objects[key]
