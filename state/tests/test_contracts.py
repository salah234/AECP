"""Tests for ContractRegistry.get/propose_version/freeze against
FakeStateRepository.
"""

from __future__ import annotations

import pytest

from app.contracts import ContractRegistry, InterfaceContract

from .fakes import FakeStateRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CONTRACT_ID = "contract-1"


def make_contract(*, version: int = 1, frozen: bool = False, schema: str = '{"v": 1}') -> InterfaceContract:
    return InterfaceContract(
        contract_id=CONTRACT_ID,
        tenant_id=TENANT_ID,
        name="TaskNode",
        schema=schema,
        version=version,
        frozen=frozen,
    )


async def test_get_returns_none_when_contract_does_not_exist() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    assert await registry.get("missing") is None


async def test_get_returns_the_highest_version() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    await repository.save_contract(make_contract(version=1))
    await repository.save_contract(make_contract(version=2, schema='{"v": 2}'))

    contract = await registry.get(CONTRACT_ID)

    assert contract is not None
    assert contract.version == 2
    assert contract.schema == '{"v": 2}'


async def test_propose_version_creates_new_unfrozen_version() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    await repository.save_contract(make_contract(version=1, frozen=True))

    new_version = await registry.propose_version(
        CONTRACT_ID,
        new_schema='{"v": 2}',
        proposed_by_task_id="task-1",
    )

    assert new_version.version == 2
    assert new_version.frozen is False
    assert new_version.schema == '{"v": 2}'

    # Persisted, and the prior (frozen) version is untouched.
    stored = await repository.get_contract_version(CONTRACT_ID, 2)
    assert stored == new_version
    original = await repository.get_contract_version(CONTRACT_ID, 1)
    assert original is not None
    assert original.frozen is True


async def test_propose_version_raises_when_contract_does_not_exist() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    with pytest.raises(ValueError, match="Contract doesn't exist"):
        await registry.propose_version(
            "missing",
            new_schema='{"v": 1}',
            proposed_by_task_id="task-1",
        )


async def test_freeze_marks_version_frozen_and_persists() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    await repository.save_contract(make_contract(version=1, frozen=False))

    frozen = await registry.freeze(CONTRACT_ID, 1)

    assert frozen.frozen is True

    stored = await repository.get_contract_version(CONTRACT_ID, 1)
    assert stored is not None
    assert stored.frozen is True


async def test_freeze_is_idempotent_on_an_already_frozen_version() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    await repository.save_contract(make_contract(version=1, frozen=True))

    frozen_again = await registry.freeze(CONTRACT_ID, 1)

    assert frozen_again.frozen is True
    stored = await repository.get_contract_version(CONTRACT_ID, 1)
    assert stored is not None
    assert stored.frozen is True
    # Only a single row for (contract_id, version) exists — freeze() is a
    # save, not an append.
    assert len(repository.contracts) == 1


async def test_freeze_raises_when_version_does_not_exist() -> None:
    repository = FakeStateRepository()
    registry = ContractRegistry(repository)

    await repository.save_contract(make_contract(version=1))

    with pytest.raises(ValueError, match="Contract version doesn't exist"):
        await registry.freeze(CONTRACT_ID, 99)
