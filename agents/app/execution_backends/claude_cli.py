"""ExecutionBackend implementation that runs the real `claude` CLI as a
subprocess. The default backend (AGENT_EXECUTION_BACKEND=claude_cli) — per
CLAUDE.md, AECP treats single-agent execution "as a primitive (via Claude
Code / equivalent), not something to reinvent," so this wraps the CLI
rather than building an LLM harness for it.

THIS RUNS WITH NO PER-SESSION PROCESS/FILESYSTEM ISOLATION YET.
sandbox.py's "not a security boundary" caveat is load-bearing here: this
subprocess has real tool access within the same OS process/filesystem the
Agent Pool container itself runs in, scoped only by --add-dir/cwd and a
restrictive --allowedTools default. See security/THREAT_MODEL.md and
docs/adr/0009-agent-sandbox-isolation-technology.md (still open) — this
feature raises that ADR's urgency, it does not resolve it. Never default
to --allow-dangerously-skip-permissions/bypassPermissions given that.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass

from app.execution_backends.base import ExecutionOutcome

logger = logging.getLogger(__name__)

# claude's stdout/stderr may contain task descriptions or model output
# derived from tenant code — truncate before it ever leaves this process
# via a blocker/completion RPC payload (security/THREAT_MODEL.md, threat
# #4: secret/content exposure via logs).
_MAX_REPORTED_OUTPUT_CHARS = 4000


@dataclass
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str


async def _run_subprocess(
    argv: list[str], *, cwd: str, timeout: float, env: dict[str, str]
) -> SubprocessResult:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise
    return SubprocessResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


class ClaudeCliBackend:
    """Implements ExecutionBackend by shelling out to the real `claude`
    CLI. subprocess_runner is injectable (defaults to _run_subprocess) —
    tests supply a fake matching the same async signature, the same
    constructor-injection convention every other module in this repo
    already uses (e.g. LifecycleManager's injected now_fn).
    """

    def __init__(
        self,
        *,
        claude_binary: str,
        anthropic_api_key: str,
        agent_model: str,
        permission_mode: str,
        allowed_tools: str,
        subprocess_runner=None,
    ) -> None:
        self._claude_binary = claude_binary
        self._anthropic_api_key = anthropic_api_key
        self._agent_model = agent_model
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools
        self._runner = subprocess_runner or _run_subprocess

    async def run(
        self, *, prompt: str, repo_dir: str, timeout_seconds: float
    ) -> ExecutionOutcome:
        if not self._anthropic_api_key:
            return ExecutionOutcome(
                success=False,
                summary="",
                rationale="ANTHROPIC_API_KEY not configured; cannot execute agent",
            )

        try:
            result = await self._runner(
                [
                    self._claude_binary,
                    "-p",
                    prompt,
                    "--output-format",
                    "json",
                    "--add-dir",
                    repo_dir,
                    "--permission-mode",
                    self._permission_mode,
                    "--allowedTools",
                    self._allowed_tools,
                    "--model",
                    self._agent_model,
                ],
                cwd=repo_dir,
                timeout=timeout_seconds,
                env={
                    # The agents container's nonroot user has no home
                    # directory (Dockerfile: useradd --no-create-home), so
                    # claude's own config/credential storage needs somewhere
                    # writable to point at — repo_dir's parent (the session's
                    # scratch dir) is guaranteed to exist and conveniently
                    # keeps that state scoped per-session rather than
                    # shared/stale across sessions.
                    "HOME": os.path.dirname(repo_dir) or repo_dir,
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "ANTHROPIC_API_KEY": self._anthropic_api_key,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the ExecutionBackend contract: never raise for an execution-level failure
            return ExecutionOutcome(success=False, summary="", rationale=f"claude execution failed: {exc}")

        if result.returncode != 0:
            return ExecutionOutcome(
                success=False,
                summary="",
                rationale=f"claude exited {result.returncode}: {_truncate(result.stderr)}",
            )

        summary, rationale, is_error = _parse_result(result.stdout)
        if is_error:
            # Verified empirically against the installed CLI: a run can
            # exit 0 while its --output-format json payload still carries
            # is_error=true (e.g. the model gave up without a tool
            # failure) — returncode alone isn't a reliable success signal.
            return ExecutionOutcome(
                success=False, summary="", rationale=f"claude reported an error: {rationale}"
            )

        return ExecutionOutcome(success=True, summary=summary, rationale=rationale)


def _parse_result(stdout: str) -> tuple[str, str, bool]:
    """Parse claude's --output-format json result into a (summary,
    rationale, is_error) tuple. The exact schema (top-level `result` and
    `is_error` fields) was verified empirically against the installed
    CLI before shipping this; falls back to raw truncated stdout with
    is_error=False if the shape ever changes underneath us, rather than
    crashing a successful run.
    """
    try:
        payload = json.loads(stdout)
        is_error = bool(payload.get("is_error", False))
        result_text = payload.get("result", "")
        if result_text:
            summary = result_text.splitlines()[0][:200]
            return summary, _truncate(result_text), is_error
    except (json.JSONDecodeError, AttributeError):
        pass
    return "Task completed", _truncate(stdout), False


def _truncate(text: str) -> str:
    if len(text) <= _MAX_REPORTED_OUTPUT_CHARS:
        return text
    return text[:_MAX_REPORTED_OUTPUT_CHARS] + "... [truncated]"
