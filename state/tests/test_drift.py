"""Tests for DriftDetector.check_module/report/resolve.

check_module() is real, correct domain logic, but is not currently wired
to the gRPC surface (ReportDrift persists a caller-supplied DriftReport
directly rather than computing one via check_module()) — same category as
taskgraph/app/risk_tier.py's can_auto_merge/is_valid_escalation. It's
still worth covering at the unit level even though nothing calls it today,
which is why this file drives DriftDetector directly rather than through
StateServicer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contracts import ContractRegistry, InterfaceContract
from app.decision_log import DecisionLog, DecisionLogEntry
from app.drift import DriftDetector, DriftReport, ModuleState
from app.ownership_map import OwnershipRecord

from .fakes import FakeStateRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CONTRACT_ID = "contract-1"
MODULE_PATH = "state/app/repository.py"


def make_detector(repository: FakeStateRepository) -> DriftDetector:
    return DriftDetector(
        contract_registry=ContractRegistry(repository),
        decision_log=DecisionLog(repository),
        repository=repository,
    )


async def test_check_module_raises_when_contract_not_found() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    with pytest.raises(ValueError, match="Contract Not Found"):
        await detector.check_module(TENANT_ID, "missing-contract", MODULE_PATH)


async def test_check_module_raises_when_module_state_not_found() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    await repository.save_contract(
        InterfaceContract(
            contract_id=CONTRACT_ID,
            tenant_id=TENANT_ID,
            name="TaskNode",
            schema='{"v": 1}',
            version=1,
            frozen=True,
        )
    )

    with pytest.raises(ValueError, match="Module state is not found"):
        await detector.check_module(TENANT_ID, CONTRACT_ID, MODULE_PATH)


async def test_check_module_returns_none_when_schemas_match() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    await repository.save_contract(
        InterfaceContract(
            contract_id=CONTRACT_ID,
            tenant_id=TENANT_ID,
            name="TaskNode",
            schema='{"v": 1}',
            version=1,
            frozen=True,
        )
    )
    await repository.save_module_state(
        ModuleState(
            tenant_id=TENANT_ID,
            module_path=MODULE_PATH,
            contract_id=CONTRACT_ID,
            current_schema='{"v": 1}',
        )
    )

    assert await detector.check_module(TENANT_ID, CONTRACT_ID, MODULE_PATH) is None


async def test_check_module_returns_report_when_schemas_disagree() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    await repository.save_contract(
        InterfaceContract(
            contract_id=CONTRACT_ID,
            tenant_id=TENANT_ID,
            name="TaskNode",
            schema='{"v": 2}',
            version=2,
            frozen=True,
        )
    )
    await repository.save_module_state(
        ModuleState(
            tenant_id=TENANT_ID,
            module_path=MODULE_PATH,
            contract_id=CONTRACT_ID,
            current_schema='{"v": 1}',
        )
    )

    report = await detector.check_module(TENANT_ID, CONTRACT_ID, MODULE_PATH)

    assert report is not None
    assert report.tenant_id == TENANT_ID
    assert report.contract_id == CONTRACT_ID
    assert report.resolved is False
    assert MODULE_PATH in report.description
    assert CONTRACT_ID in report.description


async def test_check_module_report_mentions_previous_decisions_when_present() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    await repository.save_contract(
        InterfaceContract(
            contract_id=CONTRACT_ID,
            tenant_id=TENANT_ID,
            name="TaskNode",
            schema='{"v": 2}',
            version=2,
            frozen=True,
        )
    )
    await repository.save_module_state(
        ModuleState(
            tenant_id=TENANT_ID,
            module_path=MODULE_PATH,
            contract_id=CONTRACT_ID,
            current_schema='{"v": 1}',
        )
    )
    await repository.upsert_ownership(
        OwnershipRecord(
            tenant_id=TENANT_ID,
            module_path=MODULE_PATH,
            last_task_id="task-1",
            last_agent_id="agent-1",
            last_touched_at=datetime.now(UTC),
        )
    )
    await repository.insert_decision(
        DecisionLogEntry(
            entry_id="entry-1",
            tenant_id=TENANT_ID,
            task_id="task-1",
            summary="Chose schema v1",
            rationale="...",
            decided_by_kind="KIND_AGENT",
            decided_by_id="agent-1",
            decided_at=datetime.now(UTC),
        )
    )

    report = await detector.check_module(TENANT_ID, CONTRACT_ID, MODULE_PATH)

    assert report is not None
    assert "Previous decisions found: 1" in report.description


async def test_report_persists_and_returns_the_report() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    drift = DriftReport(
        report_id="report-1",
        tenant_id=TENANT_ID,
        contract_id=CONTRACT_ID,
        description="drifted",
        resolved=False,
    )

    returned = await detector.report(drift)

    assert returned == drift
    assert repository.drift_reports["report-1"] == drift


async def test_resolve_marks_report_resolved() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    await detector.report(
        DriftReport(
            report_id="report-1",
            tenant_id=TENANT_ID,
            contract_id=CONTRACT_ID,
            description="drifted",
            resolved=False,
        )
    )

    resolved = await detector.resolve("report-1")

    assert resolved.resolved is True
    assert repository.drift_reports["report-1"].resolved is True


async def test_resolve_raises_for_unknown_report() -> None:
    repository = FakeStateRepository()
    detector = make_detector(repository)

    with pytest.raises(ValueError, match="Drift Report is None and not exist."):
        await detector.resolve("missing-report")
