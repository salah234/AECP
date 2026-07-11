"""Execution sandboxing for agent workers.

Security boundary: an agent session executes untrusted, model-generated
actions (shell commands, file edits, network calls) and must be isolated
so a compromised or misbehaving agent cannot reach another tenant's data,
another agent's sandbox, or infrastructure outside its declared ownership
boundary. Concretely: no shared filesystem, no shared network namespace,
egress restricted to declared dependencies only, resource limits enforced.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SandboxHandle:
    sandbox_id: str
    session_id: str


class Sandbox:
    def __init__(self, image: str) -> None:
        raise NotImplementedError

    async def create(self, session_id: str, tenant_id: str, ownership_globs: list[str]) -> SandboxHandle:
        """Provision an isolated execution environment scoped to exactly
        one session: no network egress beyond declared dependencies, no
        filesystem access outside ownership_globs, enforced CPU/memory/time
        limits.
        """
        raise NotImplementedError

    async def destroy(self, handle: SandboxHandle) -> None:
        """Tear down the sandbox and securely wipe any scratch state."""
        raise NotImplementedError
