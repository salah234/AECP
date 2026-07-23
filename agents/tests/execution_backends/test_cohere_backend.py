"""Tests for CohereBackend: a hand-built tool-use loop against a fake
Cohere client, no real network calls. Response shapes here mirror what
was verified against Cohere's own docs (response.message.tool_calls,
tc.function.name/arguments, response.message.content[i].text).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.execution_backends.cohere_backend import CohereBackend


class _FakeFunction:
    def __init__(self, name: str, arguments: dict) -> None:
        self.name = name
        self.arguments = json.dumps(arguments)


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict) -> None:
        self.id = call_id
        self.function = _FakeFunction(name, arguments)


class _FakeContentPart:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, *, tool_calls=None, content=None) -> None:
        self.tool_calls = tool_calls or []
        self.content = content or []


class _FakeResponse:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class FakeCohereClient:
    """Returns each queued response in order, one per `chat()` call."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, *, model, messages, tools):
        self.calls.append({"model": model, "messages": list(messages), "tools": tools})
        if not self._responses:
            raise AssertionError("FakeCohereClient ran out of queued responses")
        return self._responses.pop(0)


def make_backend(*, cohere_api_key: str = "co-test", client=None, max_iterations: int = 20):
    return CohereBackend(
        cohere_api_key=cohere_api_key,
        cohere_model="command-a-03-2025",
        max_iterations=max_iterations,
        client=client,
    )


async def test_happy_path_writes_file_and_returns_success(tmp_path: Path) -> None:
    client = FakeCohereClient(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "call-1", "write_file", {"path": "hello.txt", "content": "hi"}
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=[_FakeContentPart("Wrote hello.txt")])),
        ]
    )
    backend = make_backend(client=client)

    outcome = await backend.run(
        prompt="write hello.txt", repo_dir=str(tmp_path), timeout_seconds=5.0
    )

    assert outcome.success is True
    assert outcome.summary == "Wrote hello.txt"
    assert (tmp_path / "hello.txt").read_text() == "hi"
    assert len(client.calls) == 2
    # second call's messages must include the tool result for call-1
    tool_messages = [m for m in client.calls[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"]
    assert tool_messages[0]["tool_call_id"] == "call-1"


async def test_missing_api_key_fails_without_calling_client() -> None:
    client = FakeCohereClient([])
    backend = make_backend(cohere_api_key="", client=client)

    outcome = await backend.run(prompt="do the task", repo_dir="/fake/repo", timeout_seconds=5.0)

    assert outcome.success is False
    assert "COHERE_API_KEY" in outcome.rationale
    assert client.calls == []


async def test_iteration_cap_exceeded_fails(tmp_path: Path) -> None:
    # Always requests a (harmless, real) tool call, never finishes.
    responses = [
        _FakeResponse(
            _FakeMessage(tool_calls=[_FakeToolCall(f"call-{i}", "run_git", {"args": ["status"]})])
        )
        for i in range(5)
    ]
    client = FakeCohereClient(responses)
    backend = make_backend(client=client, max_iterations=3)

    # tmp_path isn't a real git repo, so run_git will error internally —
    # that's fine, the loop just keeps going since it never runs out of
    # tool_calls until the iteration cap kicks in.
    outcome = await backend.run(prompt="loop forever", repo_dir=str(tmp_path), timeout_seconds=5.0)

    assert outcome.success is False
    assert "max tool-use iterations" in outcome.rationale
    assert len(client.calls) == 3


async def test_tool_execution_error_reported_back_and_loop_continues(tmp_path: Path) -> None:
    client = FakeCohereClient(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[_FakeToolCall("call-1", "read_file", {"path": "does-not-exist.txt"})]
                )
            ),
            _FakeResponse(_FakeMessage(content=[_FakeContentPart("Gave up, file was missing.")])),
        ]
    )
    backend = make_backend(client=client)

    outcome = await backend.run(prompt="read a file", repo_dir=str(tmp_path), timeout_seconds=5.0)

    assert outcome.success is True  # the model itself decided to stop; that's not a backend failure
    tool_messages = [m for m in client.calls[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"]
    result_data = tool_messages[0]["content"][0]["document"]["data"]
    assert "error" in result_data
    assert "no such file" in result_data


async def test_write_file_path_escaping_repo_root_is_rejected(tmp_path: Path) -> None:
    client = FakeCohereClient(
        [
            _FakeResponse(
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall(
                            "call-1",
                            "write_file",
                            {"path": "../../etc/pwned.txt", "content": "malicious"},
                        )
                    ]
                )
            ),
            _FakeResponse(_FakeMessage(content=[_FakeContentPart("Could not write outside repo.")])),
        ]
    )
    backend = make_backend(client=client)

    outcome = await backend.run(
        prompt="escape the sandbox", repo_dir=str(tmp_path), timeout_seconds=5.0
    )

    assert outcome.success is True
    assert not (tmp_path.parent.parent / "etc" / "pwned.txt").exists()
    tool_messages = [m for m in client.calls[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"]
    result_data = tool_messages[0]["content"][0]["document"]["data"]
    assert "escapes the repository root" in result_data
