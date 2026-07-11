"""Interface contracts: the boundaries agents must not silently change.

A contract is a versioned, explicit schema (not an emergent convention
inferred from context). Tier 3 (architectural) changes are required to
touch a frozen contract; anything else touching one should be flagged by
the drift detector.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InterfaceContract:
    contract_id: str
    tenant_id: str
    name: str
    schema: str
    version: int
    frozen: bool


class ContractRegistry:
    def __init__(self, repository) -> None:
        raise NotImplementedError

    async def get(self, contract_id: str) -> InterfaceContract | None:
        raise NotImplementedError

    async def propose_version(self, contract_id: str, new_schema: str, proposed_by_task_id: str) -> InterfaceContract:
        """Create a new (unfrozen) version of a contract. Freezing it is a
        separate, explicit action requiring Tier 3 approval.
        """
        raise NotImplementedError

    async def freeze(self, contract_id: str, version: int) -> InterfaceContract:
        raise NotImplementedError
