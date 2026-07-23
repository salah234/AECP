"""In-memory test doubles for agents components.

Used to exercise AgentPoolServicer end-to-end against real
LifecycleManager/ContextHydrator/HandoffCoordinator logic without a live
sandbox, mTLS server, or State/Coordinator gRPC connection.
"""

from __future__ import annotations

import asyncio

from app.sandbox import SandboxHandle


class FakeSandbox:
    """Implements Sandbox's async interface without touching the
    filesystem, so lifecycle tests run fast and don't leak temp dirs.

    Returns real SandboxHandle instances (not a bare dict) so callers
    that read handle.scratch_dir (e.g. grpc_server.SpawnSession wiring
    AgentExecutor.spawn_background) work the same against this fake as
    against the real Sandbox.
    """

    def __init__(self) -> None:
        self.created: dict[str, list[str]] = {}
        self.destroyed: list[str] = []

    async def create(self, session_id: str, tenant_id: str, ownership_globs: list[str]):
        self.created[session_id] = ownership_globs
        return SandboxHandle(
            sandbox_id=f"fake-sandbox-{session_id}",
            session_id=session_id,
            scratch_dir=f"/fake/scratch/{session_id}",
        )

    async def destroy(self, handle) -> None:
        self.destroyed.append(handle.session_id)


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
        self.reported_completions: list[dict] = []

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

    async def report_completion(
        self, *, task_id: str, tenant_id: str, agent_id: str, summary: str, rationale: str
    ) -> bool:
        self.reported_completions.append(
            {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "summary": summary,
                "rationale": rationale,
            }
        )
        return True


class FakeTargetRepoCheckout:
    """Implements TargetRepoCheckout's async interface without touching
    git or the filesystem.
    """

    def __init__(self, *, checkout_dir: str = "/fake/scratch/repo", fail: bool = False) -> None:
        self.checkout_dir = checkout_dir
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def checkout(self, scratch_dir: str, session_id: str) -> str:
        self.calls.append((scratch_dir, session_id))
        if self.fail:
            raise RuntimeError("simulated checkout failure")
        return self.checkout_dir


class FakeSubprocessRunner:
    """Implements ClaudeCliBackend's injectable subprocess_runner signature
    without spawning a real process. `result` is returned verbatim unless
    `hang_event` is set, in which case the call blocks until cancelled —
    used to exercise AgentExecutor.cancel()/shutdown() actually
    interrupting an in-flight run.
    """

    def __init__(self, *, result=None, hang_event: asyncio.Event | None = None) -> None:
        from app.execution_backends.claude_cli import SubprocessResult

        self.result = result or SubprocessResult(returncode=0, stdout="{}", stderr="")
        self.hang_event = hang_event
        self.calls: list[dict] = []

    async def __call__(self, argv, *, cwd, timeout, env):
        self.calls.append({"argv": argv, "cwd": cwd, "timeout": timeout})
        if self.hang_event is not None:
            await self.hang_event.wait()
        return self.result


class FakeExecutionBackend:
    """Implements ExecutionBackend's async interface without invoking any
    real backend. `outcome` is returned verbatim unless `hang_event` is
    set, in which case the call blocks until cancelled — used by
    test_executor.py to exercise AgentExecutor's own orchestration
    (hydrate/checkout/report branching, cancellation) independent of any
    concrete backend.
    """

    def __init__(self, *, outcome=None, hang_event: asyncio.Event | None = None) -> None:
        from app.execution_backends.base import ExecutionOutcome

        self.outcome = outcome or ExecutionOutcome(success=True, summary="ok", rationale="ok")
        self.hang_event = hang_event
        self.calls: list[dict] = []

    async def run(self, *, prompt: str, repo_dir: str, timeout_seconds: float):
        self.calls.append({"prompt": prompt, "repo_dir": repo_dir, "timeout_seconds": timeout_seconds})
        if self.hang_event is not None:
            await self.hang_event.wait()
        return self.outcome


class FakeExecutor:
    """Spy double for AgentExecutor: records spawn_background calls
    without starting any real background task or subprocess. Used by
    grpc_server/handoff tests that only need to assert *that* execution
    was kicked off, not exercise AgentExecutor's own run/cancel logic
    (see test_executor.py for that).
    """

    def __init__(self) -> None:
        self.spawn_background_calls: list[tuple[str, str]] = []

    def spawn_background(self, session, scratch_dir: str) -> None:
        self.spawn_background_calls.append((session.session_id, scratch_dir))

    async def cancel(self, session_id: str) -> None:
        pass


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
    "FakeExecutionBackend",
    "FakeExecutor",
    "FakeIdentityIssuer",
    "FakeSandbox",
    "FakeStateClient",
    "FakeSubprocessRunner",
    "FakeTargetRepoCheckout",
]
