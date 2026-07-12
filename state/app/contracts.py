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
    tenant_id: str # Multi-tenant
    name: str
    schema: str
    version: int
    frozen: bool


class ContractRegistry:
    def __init__(self, repository) -> None: # Repo is like a person who knows where the data is stored.
        self.repository = repository

    async def get(self, contract_id: str) -> InterfaceContract | None:
        return await self.repository.get_contract(contract_id)

    async def propose_version(self, contract_id: str, new_schema: str, proposed_by_task_id: str) -> InterfaceContract:
        """Create a new (unfrozen) version of a contract. Freezing it is a
        separate, explicit action requiring Tier 3 approval.
        """
        
        current_contract = await self.repository.get_contract(contract_id)
        if current_contract is None:
            raise ValueError("Contract doesn't exist")
        new_contract = InterfaceContract(
            contract_id=current_contract.contract_id,
            tenant_id=current_contract.tenant_id,
            name=current_contract.name,
            schema=new_schema,
            version=current_contract.version + 1,
            frozen=False
        )
        await self.repository.save_contract(new_contract)
        return new_contract
        
    async def freeze(self, contract_id: str, version: int) -> InterfaceContract:
        current_contract = await self.repository.get_contract_version(contract_id, version)
        if current_contract is None:
            raise ValueError("Contract version doesn't exist")

        current_contract.frozen = True 
        await self.repository.save_contract(current_contract)
        return current_contract



