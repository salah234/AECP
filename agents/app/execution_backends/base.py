"""The pluggable interface every agent execution backend implements.

Follows this repo's existing pluggable-backend convention
(platform/aecp_platform/secrets.SecretProvider — a typing.Protocol) rather
than inventing a new abstraction style. AgentExecutor (executor.py) depends
only on this Protocol, never on a concrete backend, so swapping the default
claude CLI backend for another (e.g. Cohere) is a wiring change in main.py,
not a code change here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExecutionOutcome:
    success: bool
    summary: str
    rationale: str  # on failure, this is the blocker description


class ExecutionBackend(Protocol):
    async def run(
        self, *, prompt: str, repo_dir: str, timeout_seconds: float
    ) -> ExecutionOutcome:
        """Run one session's task to completion (or failure) against the
        already-checked-out repo_dir, and return the outcome. Must never
        raise for an execution-level failure (bad model output, tool
        error, timeout) — those become ExecutionOutcome(success=False,
        ...) so AgentExecutor can report a blocker uniformly across
        backends. asyncio.CancelledError should still propagate (session
        torn down mid-flight), not be swallowed into a failed outcome.
        """
        ...
