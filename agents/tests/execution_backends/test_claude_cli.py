"""Tests for ClaudeCliBackend: running the claude CLI via an injectable
subprocess runner, no real subprocess or network calls.
"""

from __future__ import annotations

import asyncio
import json

from app.execution_backends.claude_cli import ClaudeCliBackend, SubprocessResult

from ..fakes import FakeSubprocessRunner


def make_backend(*, anthropic_api_key: str = "sk-test", subprocess_runner=None):
    return ClaudeCliBackend(
        claude_binary="claude",
        anthropic_api_key=anthropic_api_key,
        agent_model="sonnet",
        permission_mode="acceptEdits",
        allowed_tools="Read Edit Write Bash(git *)",
        subprocess_runner=subprocess_runner,
    )


async def test_happy_path_returns_success_outcome() -> None:
    runner = FakeSubprocessRunner(
        result=SubprocessResult(
            returncode=0,
            stdout=json.dumps({"result": "Added exponential backoff to webhook retries."}),
            stderr="",
        )
    )
    backend = make_backend(subprocess_runner=runner)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is True
    assert outcome.summary == "Added exponential backoff to webhook retries."
    assert outcome.rationale == "Added exponential backoff to webhook retries."
    assert len(runner.calls) == 1
    assert "--add-dir" in runner.calls[0]["argv"]


async def test_missing_api_key_fails_without_running() -> None:
    runner = FakeSubprocessRunner()
    backend = make_backend(anthropic_api_key="", subprocess_runner=runner)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is False
    assert "ANTHROPIC_API_KEY" in outcome.rationale
    assert runner.calls == []


async def test_nonzero_exit_fails() -> None:
    runner = FakeSubprocessRunner(
        result=SubprocessResult(returncode=1, stdout="", stderr="permission denied")
    )
    backend = make_backend(subprocess_runner=runner)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is False
    assert "permission denied" in outcome.rationale


async def test_is_error_payload_fails_even_with_zero_exit() -> None:
    runner = FakeSubprocessRunner(
        result=SubprocessResult(
            returncode=0,
            stdout=json.dumps({"result": "gave up", "is_error": True}),
            stderr="",
        )
    )
    backend = make_backend(subprocess_runner=runner)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is False
    assert "gave up" in outcome.rationale


async def test_runner_exception_fails_outcome_instead_of_raising() -> None:
    async def _raising_runner(argv, *, cwd, timeout, env):
        raise OSError("no such file or directory: claude")

    backend = make_backend(subprocess_runner=_raising_runner)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is False
    assert "no such file or directory" in outcome.rationale


async def test_hang_can_be_cancelled() -> None:
    hang_event = asyncio.Event()
    runner = FakeSubprocessRunner(hang_event=hang_event)
    backend = make_backend(subprocess_runner=runner)

    task = asyncio.create_task(
        backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)
    )
    await asyncio.sleep(0)
    task.cancel()

    try:
        await task
        raise AssertionError("expected CancelledError")
    except asyncio.CancelledError:
        pass
