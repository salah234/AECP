"""ExecutionBackend implementation backed by Cohere's Chat API v2.

Cohere ships no equivalent of the `claude` CLI — no built-in agentic
file-edit/bash loop — so unlike ClaudeCliBackend, this module *is* a small
hand-built tool-use harness: define tools, send them, get tool-call
requests back, execute them against the checked-out worktree, send
results back, repeat until the model stops requesting tools. Selected via
AGENT_EXECUTION_BACKEND=cohere (agents/app/config.py); claude_cli remains
the default.

Tool set is deliberately as restrictive as ClaudeCliBackend's default
`--allowedTools "Read Edit Write Bash(git *)"`: file read/write/edit
scoped to repo_dir only, and `git` invoked via argv (never a shell), no
network-capable tools. Every file-tool path is resolved and checked to
stay inside repo_dir before any read/write — the equivalent of the claude
CLI's --add-dir scoping. Same "no per-session process isolation yet"
caveat as claude_cli.py applies here too (security/THREAT_MODEL.md,
docs/adr/0009-agent-sandbox-isolation-technology.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.execution_backends.base import ExecutionOutcome

logger = logging.getLogger(__name__)

_MAX_REPORTED_OUTPUT_CHARS = 4000
_MAX_TOOL_RESULT_CHARS = 8000

_SYSTEM_PROMPT = (
    "You are an autonomous engineering agent. Use the provided tools to read, "
    "write, and edit files within the given repository, and to run git "
    "commands to inspect/commit your work. When you are completely finished, "
    "respond with a final message (no further tool calls) giving a concise "
    "summary of exactly what you changed and why."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents, path relative to the repo root.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file, path relative to the repo root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace an exact substring in an existing file, path relative to "
                "the repo root. old_text must match exactly once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_git",
            "description": "Run a git command in the repo (e.g. args: [\"add\", \"-A\"]).",
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["args"],
            },
        },
    },
]


class _ToolError(Exception):
    pass


class CohereBackend:
    """Implements ExecutionBackend via a Cohere Chat API v2 tool-use loop.

    client is injectable (defaults to cohere.AsyncClientV2(cohere_api_key))
    — tests supply a fake exposing the same async `chat(...)` signature,
    mirroring ClaudeCliBackend's subprocess_runner injection.
    """

    def __init__(
        self,
        *,
        cohere_api_key: str,
        cohere_model: str,
        max_iterations: int,
        client=None,
    ) -> None:
        self._cohere_api_key = cohere_api_key
        self._cohere_model = cohere_model
        self._max_iterations = max_iterations
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        import cohere

        return cohere.AsyncClientV2(self._cohere_api_key)

    async def run(
        self, *, prompt: str, repo_dir: str, timeout_seconds: float
    ) -> ExecutionOutcome:
        if not self._cohere_api_key:
            return ExecutionOutcome(
                success=False, summary="", rationale="COHERE_API_KEY not configured; cannot execute agent"
            )

        try:
            return await asyncio.wait_for(
                self._run_loop(prompt=prompt, repo_dir=repo_dir), timeout=timeout_seconds
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return ExecutionOutcome(
                success=False, summary="", rationale=f"Cohere run exceeded {timeout_seconds}s timeout"
            )
        except Exception as exc:  # noqa: BLE001 - any failure here must degrade to a blocker
            logger.exception("CohereBackend run failed")
            return ExecutionOutcome(success=False, summary="", rationale=f"Cohere run failed: {exc}")

    async def _run_loop(self, *, prompt: str, repo_dir: str) -> ExecutionOutcome:
        client = self._get_client()
        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        for _iteration in range(self._max_iterations):
            response = await client.chat(model=self._cohere_model, messages=messages, tools=_TOOLS)
            tool_calls = response.message.tool_calls

            if not tool_calls:
                final_text = _extract_text(response)
                summary = final_text.splitlines()[0][:200] if final_text else "Task completed"
                return ExecutionOutcome(
                    success=True, summary=summary, rationale=_truncate(final_text)
                )

            messages.append(response.message)
            for tool_call in tool_calls:
                result_text = await self._execute_tool(tool_call, repo_dir)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": [{"type": "document", "document": {"data": result_text}}],
                    }
                )

        return ExecutionOutcome(
            success=False,
            summary="",
            rationale=f"Exceeded max tool-use iterations ({self._max_iterations}) without finishing",
        )

    async def _execute_tool(self, tool_call, repo_dir: str) -> str:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            return f"error: could not parse arguments: {exc}"

        try:
            if name == "read_file":
                return _truncate_tool_result(_read_file(repo_dir, args["path"]))
            if name == "write_file":
                _write_file(repo_dir, args["path"], args["content"])
                return "ok"
            if name == "edit_file":
                _edit_file(repo_dir, args["path"], args["old_text"], args["new_text"])
                return "ok"
            if name == "run_git":
                return _truncate_tool_result(await _run_git(repo_dir, args.get("args", [])))
            return f"error: unknown tool '{name}'"
        except _ToolError as exc:
            return f"error: {exc}"
        except OSError as exc:
            return f"error: {exc}"


def _resolve_in_repo(repo_dir: str, relative_path: str) -> Path:
    repo_root = Path(repo_dir).resolve()
    candidate = (repo_root / relative_path).resolve()
    if candidate != repo_root and repo_root not in candidate.parents:
        raise _ToolError(f"path '{relative_path}' escapes the repository root")
    return candidate


def _read_file(repo_dir: str, relative_path: str) -> str:
    path = _resolve_in_repo(repo_dir, relative_path)
    if not path.is_file():
        raise _ToolError(f"no such file: {relative_path}")
    return path.read_text(errors="replace")


def _write_file(repo_dir: str, relative_path: str, content: str) -> None:
    path = _resolve_in_repo(repo_dir, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _edit_file(repo_dir: str, relative_path: str, old_text: str, new_text: str) -> None:
    path = _resolve_in_repo(repo_dir, relative_path)
    if not path.is_file():
        raise _ToolError(f"no such file: {relative_path}")
    original = path.read_text()
    occurrences = original.count(old_text)
    if occurrences != 1:
        raise _ToolError(
            f"old_text must match exactly once in {relative_path}, found {occurrences}"
        )
    path.write_text(original.replace(old_text, new_text, 1))


async def _run_git(repo_dir: str, args: list[str]) -> str:
    # asyncio.create_subprocess_exec (argv form, never shell=True) rules
    # out shell injection regardless of arg content — same pattern as
    # target_repo.py's own _run_git.
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=repo_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
    if proc.returncode != 0:
        raise _ToolError(f"git {' '.join(args)} exited {proc.returncode}: {output}")
    return output


def _extract_text(response) -> str:
    content = getattr(response.message, "content", None)
    if not content:
        return ""
    return "".join(getattr(part, "text", "") for part in content)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_REPORTED_OUTPUT_CHARS:
        return text
    return text[:_MAX_REPORTED_OUTPUT_CHARS] + "... [truncated]"


def _truncate_tool_result(text: str) -> str:
    if len(text) <= _MAX_TOOL_RESULT_CHARS:
        return text
    return text[:_MAX_TOOL_RESULT_CHARS] + "... [truncated]"
