"""Drift detector: flags when live code diverges from the decision log's
assumptions.

Compares the current state of a module (as reported by the Integration
layer's semantic diff, or by periodic re-scans) against the interface
contracts and decision log entries that were assumed true when it was
last touched, and raises a DriftReport when they no longer agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4



@dataclass
class DriftReport:
    report_id: str
    tenant_id: str
    contract_id: str
    description: str
    resolved: bool

@dataclass
class ModuleState:
    tenant_id: str
    module_path: str
    contract_id: str
    current_schema: str


class DriftDetector:
    def __init__(self, contract_registry, decision_log, repository) -> None:
        self.contract_registry = contract_registry
        self.repository = repository
        self.decision_log = decision_log

    async def check_module(self, tenant_id: str, contract_id: str, module_path: str) -> DriftReport | None:
        """Return a DriftReport if module_path's current state disagrees
        with the assumptions recorded for it, else None.
        """

        contract = await self.contract_registry.get(contract_id)
        if contract is None:
            raise ValueError('Contract Not Found') 
    
        module_state = await self.repository.get_module_state(
            tenant_id, module_path
        )
        if module_state is None:
            raise ValueError('Module state is not found')
        if module_state.current_schema == contract.schema:
            return None # No Drift
        
        decisions = await self.decision_log.history_for_module(
            tenant_id,
            module_path,
        )


        description = (
            f"Module {module_path} drifted from "
            f"contract {contract.contract_id}. "
            f"Expected schema version {contract.version}, "
            f"but current module schema differs."
        )

        if decisions:
            description += (
                f" Previous decisions found: {len(decisions)}."
            )

        return DriftReport(
            report_id=str(uuid4()),
            tenant_id=tenant_id,
            contract_id=contract.contract_id,
            description=description,
            resolved=False,
        )
    

    async def report(self, report: DriftReport) -> DriftReport:
        await self.repository.insert_drift_report(report)
        return report

    async def resolve(self, report_id: str) -> DriftReport:
        report = await self.repository.get_drift_report(report_id)
        if report is None:
            raise ValueError('Drift Report is None and not exist.')

        report.resolved = True 

        await self.repository.update_drift_report(report)
        return report
        
