"""Execution sandboxing for agent workers.

Security boundary: an agent session executes untrusted, model-generated
actions (shell commands, file edits, network calls) and must be isolated
so a compromised or misbehaving agent cannot reach another tenant's data,
another agent's sandbox, or infrastructure outside its declared ownership
boundary. Concretely: no shared filesystem, no shared network namespace,
egress restricted to declared dependencies only, resource limits enforced.

/security/THREAT_MODEL.md lists the concrete sandbox technology
(gVisor/Firecracker/container-only) as an open Tier 3 decision requiring
its own ADR before implementation starts — CLAUDE.md's Escalation Policy
means this module must not unilaterally pick that technology.

THIS IMPLEMENTATION IS NOT A SECURITY BOUNDARY. It provides no process,
filesystem, or network isolation whatsoever — it only allocates a scratch
directory per session so LifecycleManager has something real to call in
dev and tests. It exists purely so the rest of the Agent Pool (spawn,
handoff, teardown, capacity accounting) can be implemented and tested
end-to-end pending the Tier 3 ADR. Do not deploy this against real tenant
code. This mirrors the precedent set by
aecp_platform.secrets.EnvSecretProvider, which is explicitly dev/CI-only
pending its own ADR (docs/adr/0006-secrets-management.md).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class SandboxHandle:
    sandbox_id: str
    session_id: str
    scratch_dir: str


class Sandbox:
    def __init__(self, image: str) -> None:
        self.image = image
        self._handles: dict[str, SandboxHandle] = {}

    async def create(
        self, session_id: str, tenant_id: str, ownership_globs: list[str]
    ) -> SandboxHandle:
        """Provision an isolated execution environment scoped to exactly
        one session: no network egress beyond declared dependencies, no
        filesystem access outside ownership_globs, enforced CPU/memory/time
        limits.

        Dev placeholder: allocates a private scratch directory and records
        the declared ownership_globs alongside it for inspection. Enforces
        none of the above guarantees.
        """
        scratch_dir = Path(
            tempfile.mkdtemp(prefix=f"aecp-agent-{tenant_id}-{session_id}-")
        )
        (scratch_dir / "OWNERSHIP_GLOBS").write_text("\n".join(ownership_globs))

        handle = SandboxHandle(
            sandbox_id=str(uuid4()),
            session_id=session_id,
            scratch_dir=str(scratch_dir),
        )
        self._handles[session_id] = handle
        return handle

    async def destroy(self, handle: SandboxHandle) -> None:
        """Tear down the sandbox and securely wipe any scratch state."""
        self._handles.pop(handle.session_id, None)
        shutil.rmtree(handle.scratch_dir, ignore_errors=True)
