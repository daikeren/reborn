from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agent.backends.codex_backend import CodexBackend
from app.agent.types import AgentError, AgentResult


@dataclass
class _Note:
    method: str
    params: dict


class _FakeCodexClient:
    def __init__(self, notes: list[_Note], *, raise_after: Exception | None = None):
        self.notes = notes
        self.raise_after = raise_after
        self.listed_skills: list[dict] = []
        self.start_kwargs: dict | None = None
        self.resume_kwargs: dict | None = None
        self.turn_kwargs: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def list_skills(self, *, cwd: str, force_reload: bool = True):
        return self.listed_skills

    async def start_thread(self, **kwargs):
        self.start_kwargs = kwargs
        return "thread-new"

    async def resume_thread(self, **kwargs):
        self.resume_kwargs = kwargs
        return kwargs["thread_id"]

    async def stream_turn(self, **kwargs):
        self.turn_kwargs = kwargs
        for note in self.notes:
            yield note
        if self.raise_after:
            raise self.raise_after


def _completed(thread_id: str = "thread-new", turn_id: str = "turn-1") -> _Note:
    return _Note(
        "turn/completed",
        {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed"}},
    )


def _backend_with_client(fake_client: _FakeCodexClient, monkeypatch) -> CodexBackend:
    backend = CodexBackend()
    monkeypatch.setattr(backend, "create_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.agent.backends.codex_backend.build_system_prompt", lambda **kw: "prompt"
    )
    return backend


@pytest.mark.asyncio
async def test_basic_agent_turn(monkeypatch):
    notes = [
        _Note(
            "item/completed", {"item": {"type": "agentMessage", "text": "Hello world"}}
        ),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    result = await backend.agent_turn("hi")
    assert result.text == "Hello world"
    assert result.session_id == "thread-new"


@pytest.mark.asyncio
async def test_commentary_channel_is_ignored(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {
                "item": {
                    "type": "agentMessage",
                    "channel": "commentary",
                    "text": "thinking",
                }
            },
        ),
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "final"}},
        ),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    result = await backend.agent_turn("test")
    assert result.text == "final"


@pytest.mark.asyncio
async def test_missing_channel_is_treated_as_final(monkeypatch):
    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "Hello"}}),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    result = await backend.agent_turn("test")
    assert result.text == "Hello"


@pytest.mark.asyncio
async def test_multiple_final_messages_use_last_completed_text(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "draft"}},
        ),
        _Note(
            "item/completed",
            {
                "item": {
                    "type": "agentMessage",
                    "channel": "final",
                    "text": "final answer",
                }
            },
        ),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    result = await backend.agent_turn("hello")
    assert result.text == "final answer"
    assert result.session_id == "thread-new"


@pytest.mark.asyncio
async def test_multiple_final_messages_ignore_commentary_and_use_last(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "first"}},
        ),
        _Note(
            "item/completed",
            {
                "item": {
                    "type": "agentMessage",
                    "channel": "commentary",
                    "text": "thinking",
                }
            },
        ),
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "second"}},
        ),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    result = await backend.agent_turn("hello")
    assert result.text == "second"
    assert result.session_id == "thread-new"


@pytest.mark.asyncio
async def test_resume_uses_existing_session_id(monkeypatch):
    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "ok"}}),
        _completed(thread_id="thread-old"),
    ]
    client = _FakeCodexClient(notes)
    backend = _backend_with_client(client, monkeypatch)

    result = await backend.agent_turn("hello", session_id="thread-old")
    assert client.resume_kwargs is not None
    assert client.resume_kwargs["thread_id"] == "thread-old"
    assert result.session_id == "thread-old"


@pytest.mark.asyncio
async def test_partial_result_on_stream_failure(monkeypatch):
    notes = [
        _Note(
            "item/completed", {"item": {"type": "agentMessage", "text": "partial text"}}
        ),
    ]
    backend = _backend_with_client(
        _FakeCodexClient(notes, raise_after=RuntimeError("connection lost")),
        monkeypatch,
    )

    result = await backend.agent_turn("hello")
    assert result.text == "partial text"
    assert result.session_id == "thread-new"


@pytest.mark.asyncio
async def test_partial_failure_returns_latest_final_text(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "draft"}},
        ),
        _Note(
            "item/completed",
            {
                "item": {
                    "type": "agentMessage",
                    "channel": "final",
                    "text": "stable final",
                }
            },
        ),
    ]
    backend = _backend_with_client(
        _FakeCodexClient(notes, raise_after=RuntimeError("connection lost")),
        monkeypatch,
    )

    result = await backend.agent_turn("hello")
    assert result.text == "stable final"
    assert result.session_id == "thread-new"


@pytest.mark.asyncio
async def test_raises_when_no_partial_available(monkeypatch):
    backend = _backend_with_client(
        _FakeCodexClient([], raise_after=RuntimeError("connection lost")),
        monkeypatch,
    )

    with pytest.raises(AgentError):
        await backend.agent_turn("hello")


@pytest.mark.asyncio
async def test_channel_passed_to_build_system_prompt(monkeypatch):
    captured_kwargs = {}

    def _capture_prompt(**kwargs):
        captured_kwargs.update(kwargs)
        return "prompt"

    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "ok"}}),
        _completed(),
    ]
    client = _FakeCodexClient(notes)
    backend = CodexBackend()
    monkeypatch.setattr(backend, "create_client", lambda: client)
    monkeypatch.setattr(
        "app.agent.backends.codex_backend.build_system_prompt", _capture_prompt
    )

    await backend.agent_turn("hi", channel="slack")
    assert captured_kwargs.get("channel") == "slack"

    captured_kwargs.clear()
    await backend.agent_turn("hi", channel="telegram")
    assert captured_kwargs.get("channel") == "telegram"

    captured_kwargs.clear()
    await backend.agent_turn("hi")
    assert captured_kwargs.get("channel") is None


@pytest.mark.asyncio
async def test_enable_skills_adds_skill_input(monkeypatch):
    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "ok"}}),
        _completed(),
    ]
    client = _FakeCodexClient(notes)
    client.listed_skills = [
        {
            "name": "web-researcher",
            "path": "/tmp/skills/web-researcher/SKILL.md",
            "description": "Research",
        },
        {
            "name": "disabled",
            "path": "/tmp/skills/disabled/SKILL.md",
            "description": "",
        },
        {
            "name": "google-workspace",
            "path": "/tmp/skills/google-workspace/SKILL.md",
            "description": "Google Workspace",
        },
    ]

    captured_prompt_kwargs = {}

    def _capture_prompt(**kwargs):
        captured_prompt_kwargs.update(kwargs)
        return "prompt"

    backend = CodexBackend()
    monkeypatch.setattr(backend, "create_client", lambda: client)
    monkeypatch.setattr(
        "app.agent.backends.codex_backend.build_system_prompt", _capture_prompt
    )
    monkeypatch.setattr("app.agent.skills.shutil.which", lambda name: None)

    await backend.agent_turn("hello", enable_skills=True)
    assert client.turn_kwargs is not None
    input_items = client.turn_kwargs["input_items"]
    assert input_items[0]["type"] == "text"
    assert any(
        item.get("type") == "skill" and item.get("name") == "web-researcher"
        for item in input_items
    )
    assert "web-researcher" in captured_prompt_kwargs["skills"]
    assert not any(
        item.get("type") == "skill" and item.get("name") == "google-workspace"
        for item in input_items
    )
    assert "google-workspace" not in captured_prompt_kwargs["skills"]


@pytest.mark.asyncio
async def test_long_unbroken_text_is_wrapped_before_codex_calls(monkeypatch):
    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "ok"}}),
        _completed(),
    ]
    client = _FakeCodexClient(notes)
    backend = CodexBackend()
    monkeypatch.setattr(backend, "create_client", lambda: client)
    monkeypatch.setattr(
        "app.agent.backends.codex_backend.build_system_prompt",
        lambda **kw: "P" * 2100,
    )

    user_text = "M" * 2100
    await backend.agent_turn(user_text)

    assert client.start_kwargs is not None
    wrapped_prompt = client.start_kwargs["developer_instructions"]
    assert "\n" in wrapped_prompt
    assert wrapped_prompt.replace("\n", "").startswith("P" * 2100)

    assert client.turn_kwargs is not None
    wrapped_input = client.turn_kwargs["input_items"][0]["text"]
    assert "\n" in wrapped_input
    assert wrapped_input.replace("\n", "") == user_text


@pytest.mark.asyncio
async def test_sandbox_policy_includes_extra_writable_roots(
    monkeypatch, workspace: Path, external_root: Path
):
    import app.config

    old = app.config._settings

    @dataclass(frozen=True)
    class VaultSettings:
        workspace_dir: Path = workspace
        timezone: str = "Asia/Taipei"
        anthropic_api_key: str | None = None
        telegram_bot_token: str = "fake"
        allowed_telegram_user_id: int = 0
        slack_bot_token: str = "fake"
        slack_app_token: str = "fake"
        allowed_slack_user_id: str = "fake"
        agent_backend: str = "codex"
        chat_model: str = "gpt-5.4"
        background_model: str = "gpt-5.4"
        extra_writable_roots: tuple[Path, ...] = (external_root,)
        codex_app_server_command: tuple[str, ...] = ("codex", "app-server")
        codex_approval_policy: str = "never"
        codex_sandbox_mode: str = "workspace-write"
        codex_rpc_timeout_seconds: float = 60.0

    app.config._settings = VaultSettings()
    try:
        notes = [
            _Note("item/completed", {"item": {"type": "agentMessage", "text": "ok"}}),
            _completed(),
        ]
        client = _FakeCodexClient(notes)
        backend = _backend_with_client(client, monkeypatch)
        await backend.agent_turn("hello")
        roots = client.turn_kwargs["sandbox_policy"]["writableRoots"]
        assert str(workspace) in roots
        assert str(external_root) in roots
    finally:
        app.config._settings = old
