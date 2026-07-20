"""Integration-style tests for StateServicer against real DecisionLog,
OwnershipMap, ContractRegistry, and DriftDetector, backed by an in-memory
FakeStateRepository (see tests/fakes.py) instead of Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone

import grpc
import pytest

from app.contracts import ContractRegistry, InterfaceContract
from app.decision_log import DecisionLog
from app.drift import DriftDetector
from app.grpc_server import StateServicer
from app.ownership_map import OwnershipMap, OwnershipRecord
from app.common.v1 import common_pb2
from app.state.v1 import state_pb2

from .fakes import AbortedRPC, FakeContext, FakeStateRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CONTRACT_ID = "contract-1"
MODULE_PATH = "state/app/repository.py"


def make_servicer() -> tuple[StateServicer, FakeStateRepository]:
    repository = FakeStateRepository()
    servicer = StateServicer(
        decision_log=DecisionLog(repository),
        ownership_map=OwnershipMap(repository),
        contract_registry=ContractRegistry(repository),
        drift_detector=DriftDetector(
            contract_registry=ContractRegistry(repository),
            decision_log=DecisionLog(repository),
            repository=repository,
        ),
    )
    return servicer, repository


# -- RecordDecision --------------------------------------------------


async def test_record_decision_round_trips_and_converts_actor_kind() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    request = state_pb2.RecordDecisionRequest(
        entry=state_pb2.DecisionLogEntry(
            entry_id="entry-1",
            tenant_id=TENANT_ID,
            task_id="task-1",
            summary="Chose Postgres",
            rationale="Because RLS.",
            decided_by=common_pb2.Actor(
                kind=common_pb2.Actor.Kind.KIND_AGENT,
                id="agent-1",
            ),
        )
    )
    request.entry.decided_at.FromDatetime(datetime.now(timezone.utc))

    response = await servicer.RecordDecision(request, context)

    assert response.entry.entry_id == "entry-1"
    assert response.entry.summary == "Chose Postgres"
    assert response.entry.decided_by.id == "agent-1"
    assert response.entry.decided_by.kind == common_pb2.Actor.Kind.KIND_AGENT

    # Persisted with the proto enum converted to its string name, per
    # DecisionLogEntry.decided_by_kind.
    assert len(repository.decisions) == 1
    stored = repository.decisions[0]
    assert stored.decided_by_kind == "KIND_AGENT"
    assert stored.decided_by_id == "agent-1"
    assert stored.tenant_id == TENANT_ID


async def test_record_decision_converts_human_actor_kind() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    request = state_pb2.RecordDecisionRequest(
        entry=state_pb2.DecisionLogEntry(
            entry_id="entry-2",
            tenant_id=TENANT_ID,
            task_id="task-1",
            summary="Human override",
            rationale="Needed a human call.",
            decided_by=common_pb2.Actor(
                kind=common_pb2.Actor.Kind.KIND_HUMAN,
                id="human-1",
            ),
        )
    )
    request.entry.decided_at.FromDatetime(datetime.now(timezone.utc))

    await servicer.RecordDecision(request, context)

    assert repository.decisions[0].decided_by_kind == "KIND_HUMAN"


# -- GetOwnership --------------------------------------------------


async def test_get_ownership_found() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    await repository.upsert_ownership(
        OwnershipRecord(
            tenant_id=TENANT_ID,
            module_path=MODULE_PATH,
            last_task_id="task-1",
            last_agent_id="agent-1",
            last_touched_at=datetime.now(timezone.utc),
        )
    )

    response = await servicer.GetOwnership(
        state_pb2.GetOwnershipRequest(tenant_id=TENANT_ID, module_path=MODULE_PATH),
        context,
    )

    assert response.record.tenant_id == TENANT_ID
    assert response.record.module_path == MODULE_PATH
    assert response.record.last_task_id == "task-1"
    assert response.record.last_agent_id == "agent-1"


async def test_get_ownership_not_found() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.GetOwnership(
            state_pb2.GetOwnershipRequest(tenant_id=TENANT_ID, module_path="missing.py"),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


# -- GetInterfaceContract --------------------------------------------------


async def test_get_interface_contract_found() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

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

    response = await servicer.GetInterfaceContract(
        state_pb2.GetInterfaceContractRequest(contract_id=CONTRACT_ID),
        context,
    )

    assert response.contract.contract_id == CONTRACT_ID
    assert response.contract.schema == '{"v": 1}'
    assert response.contract.version == 1
    assert response.contract.frozen is True


async def test_get_interface_contract_not_found() -> None:
    servicer, _repository = make_servicer()
    context = FakeContext()

    with pytest.raises(AbortedRPC) as exc_info:
        await servicer.GetInterfaceContract(
            state_pb2.GetInterfaceContractRequest(contract_id="missing"),
            context,
        )

    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


# NOTE(tenancy) regression note: GetInterfaceContract intentionally never
# calls bind_tenant() -- GetInterfaceContractRequest carries no tenant_id
# field on the wire (see proto/state/v1/state.proto and the NOTE(tenancy)
# comment in app/grpc_server.py, also referenced in docs/adr/0007). Against
# a real TenantScopedPool this fails closed with a "no tenant bound"
# LookupError rather than running unscoped; FakeStateRepository doesn't
# enforce that, so it isn't reproducible here. This test only documents
# that the gap is known/tracked, not a bug to "fix" via this suite.
async def test_get_interface_contract_request_has_no_tenant_id_field() -> None:
    assert "tenant_id" not in state_pb2.GetInterfaceContractRequest.DESCRIPTOR.fields_by_name


# -- ReportDrift --------------------------------------------------


async def test_report_drift_round_trips_with_caller_supplied_report_id() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    response = await servicer.ReportDrift(
        state_pb2.ReportDriftRequest(
            report=state_pb2.DriftReport(
                report_id="report-1",
                tenant_id=TENANT_ID,
                contract_id=CONTRACT_ID,
                description="drifted",
                resolved=False,
            )
        ),
        context,
    )

    assert response.report.report_id == "report-1"
    assert repository.drift_reports["report-1"].description == "drifted"


async def test_report_drift_defaults_report_id_to_fresh_uuid_when_absent() -> None:
    servicer, repository = make_servicer()
    context = FakeContext()

    response = await servicer.ReportDrift(
        state_pb2.ReportDriftRequest(
            report=state_pb2.DriftReport(
                report_id="",
                tenant_id=TENANT_ID,
                contract_id=CONTRACT_ID,
                description="drifted",
                resolved=False,
            )
        ),
        context,
    )

    assert response.report.report_id != ""
    assert response.report.report_id in repository.drift_reports

    # Calling it again with another blank report_id produces a *different*
    # fresh id, proving it's generated per-call rather than reused/cached.
    second_response = await servicer.ReportDrift(
        state_pb2.ReportDriftRequest(
            report=state_pb2.DriftReport(
                report_id="",
                tenant_id=TENANT_ID,
                contract_id=CONTRACT_ID,
                description="drifted again",
                resolved=False,
            )
        ),
        context,
    )
    assert second_response.report.report_id != response.report.report_id
    assert len(repository.drift_reports) == 2
