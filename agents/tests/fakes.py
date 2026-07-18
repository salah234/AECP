"""In-memory test doubles for agents components.

Used to exercise AgentPoolServicer end-to-end against real
LifecycleManager/ContextHydrator/HandoffCoordinator logic without a live
sandbox, mTLS server, or State/Coordinator gRPC connection.
"""

from __future__ import annotations


class FakeSandbox:
    """Implements Sandbox's async interface without touching the
    filesystem, so lifecycle tests run fast and don't leak temp dirs.
    """

    def __init__(self) -> None:
        self.created: dict[str, list[str]] = {}
        self.destroyed: list[str] = []

    async def create(self, session_id: str, tenant_id: str, ownership_globs: list[str]):
        self.created[session_id] = ownership_globs
        return {"session_id": session_id}

    async def destroy(self, handle) -> None:
        self.destroyed.append(handle["session_id"])


class FakeIdentityIssuer:
    def __init__(self) -> None:
        self.issued: dict[str, int] = {}
        self.revoked: list[str] = []

    async def issue(self, session_id: str, ttl_seconds: int):
        self.issued[session_id] = ttl_seconds
        return {"session_id": session_id, "ttl_seconds": ttl_seconds}

    async def revoke(self, session_id: str) -> None:
        self.revoked.append(session_id)


class FakeStateClient:
    def __init__(self, *, fail_record_decision: bool = False) -> None:
        self.recorded_decisions: list[dict] = []
        self.fail_record_decision = fail_record_decision

    async def record_decision(self, **kwargs):
        if self.fail_record_decision:
            raise RuntimeError("simulated State outage")
        self.recorded_decisions.append(kwargs)
        return kwargs

    async def get_ownership(self, tenant_id: str, module_path: str):
        return None

    async def get_interface_contract(self, contract_id: str):
        return None


class FakeCoordinatorClient:
    def __init__(self) -> None:
        self.reported_blockers: list[dict] = []

    async def report_blocker(
        self, *, task_id: str, tenant_id: str, agent_id: str, description: str
    ) -> bool:
        self.reported_blockers.append(
            {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "description": description,
            }
        )
        return True


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


__all__ = [
    "AbortedRPC",
    "FakeContext",
    "FakeCoordinatorClient",
    "FakeIdentityIssuer",
    "FakeSandbox",
    "FakeStateClient",
]
