"""Drift detector: flags when live code diverges from the decision log's
assumptions.

Compares the current state of a module (as reported by the Integration
layer's semantic diff, or by periodic re-scans) against the interface
contracts and decision log entries that were assumed true when it was
last touched, and raises a DriftReport when they no longer agree.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DriftReport:
    report_id: str
    tenant_id: str
    contract_id: str
    description: str
    resolved: bool


class DriftDetector:
    def __init__(self, contract_registry, decision_log, repository) -> None:
        raise NotImplementedError

    async def check_module(self, tenant_id: str, module_path: str) -> DriftReport | None:
        """Return a DriftReport if module_path's current state disagrees
        with the assumptions recorded for it, else None.
        """
        raise NotImplementedError

    async def report(self, report: DriftReport) -> DriftReport:
        raise NotImplementedError

    async def resolve(self, report_id: str) -> DriftReport:
        raise NotImplementedError
