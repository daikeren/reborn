from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.agent.types import Attachment, AgentError


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeAssistantMessage:
    content: list[object]


@dataclass
class _FakeResultMessage:
    session_id: str | None
    is_error: bool
    result: str


@dataclass
class _FakeSystemMessage:
    subtype: str
    data: dict | None = None


@pytest.mark.asyncio
async def test_agent_turn_passes_extra_writable_roots_to_add_dirs(
    monkeypatch, workspace: Path, external_root: Path
):
    import app.config
    from app.agent.backends.claude_backend import ClaudeBackend

    old = app.config._settings

    @dataclass(frozen=True)
    class FakeSettings:
        workspace_dir: Path = workspace
        timezone: str = "Asia/Taipei"
        anthropic_api_key: str | None = None
        telegram_bot_token: str = "fake"
        allowed_telegram_user_id: int = 0
        slack_bot_token: str = "fake"
        slack_app_token: str = "fake"
        allowed_slack_user_id: str = "fake"
        agent_backend: str = "claude"
        chat_model: str = "claude-sonnet-4-5"
        background_model: str = "claude-sonnet-4-5"
        extra_writable_roots: tuple[Path, ...] = (external_root,)

    captured = {}

    async def _fake_query(*, prompt, options):
        captured["add_dirs"] = options.add_dirs
        captured["allowed_tools"] = options.allowed_tools
        if False:
            yield None

    app.config._settings = FakeSettings()
    try:
        backend = ClaudeBackend()
        monkeypatch.setattr("app.agent.backends.claude_backend.query", _fake_query)
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.build_system_prompt",
            lambda **kwargs: "prompt",
        )

        result = await backend.agent_turn("hello")

        assert result.text == ""
        assert captured["add_dirs"] == [str(workspace), str(external_root)]
        assert captured["allowed_tools"] == [
            "WebSearch",
            "WebFetch",
            "AskUserQuestion",
            "mcp__memory__memory_write",
            "mcp__memory__memory_search",
            "mcp__memory__memory_update_core",
            "Bash",
            "Write",
        ]
    finally:
        app.config._settings = old


@pytest.mark.asyncio
async def test_agent_turn_preserves_explicit_allowed_tools(
    monkeypatch, workspace: Path, external_root: Path
):
    import app.config
    from app.agent.backends.claude_backend import ClaudeBackend

    old = app.config._settings

    @dataclass(frozen=True)
    class FakeSettings:
        workspace_dir: Path = workspace
        timezone: str = "Asia/Taipei"
        anthropic_api_key: str | None = None
        telegram_bot_token: str = "fake"
        allowed_telegram_user_id: int = 0
        slack_bot_token: str = "fake"
        slack_app_token: str = "fake"
        allowed_slack_user_id: str = "fake"
        agent_backend: str = "claude"
        chat_model: str = "claude-sonnet-4-5"
        background_model: str = "claude-sonnet-4-5"
        extra_writable_roots: tuple[Path, ...] = (external_root,)

    captured = {}

    async def _fake_query(*, prompt, options):
        captured["allowed_tools"] = options.allowed_tools
        if False:
            yield None

    app.config._settings = FakeSettings()
    try:
        backend = ClaudeBackend()
        monkeypatch.setattr("app.agent.backends.claude_backend.query", _fake_query)
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.build_system_prompt",
            lambda **kwargs: "prompt",
        )

        result = await backend.agent_turn("hello", allowed_tools=["WebSearch"])

        assert result.text == ""
        assert captured["allowed_tools"] == ["WebSearch"]
    finally:
        app.config._settings = old


@pytest.mark.asyncio
async def test_agent_turn_retries_image_failures_without_resending_image(
    monkeypatch, workspace: Path, external_root: Path
):
    import app.config
    from app.agent.backends.claude_backend import ClaudeBackend
    from app.monitoring.types import ExecutionEventKind

    old = app.config._settings

    @dataclass(frozen=True)
    class FakeSettings:
        workspace_dir: Path = workspace
        timezone: str = "Asia/Taipei"
        anthropic_api_key: str | None = None
        telegram_bot_token: str = "fake"
        allowed_telegram_user_id: int = 0
        slack_bot_token: str = "fake"
        slack_app_token: str = "fake"
        allowed_slack_user_id: str = "fake"
        agent_backend: str = "claude"
        chat_model: str = "claude-sonnet-4-5"
        background_model: str = "claude-sonnet-4-5"
        extra_writable_roots: tuple[Path, ...] = (external_root,)

    prompt_payloads: list[object] = []
    resumes: list[str | None] = []
    events = []
    call_count = 0

    async def _capture(event):
        events.append(event)

    async def _fake_query(*, prompt, options):
        nonlocal call_count
        call_count += 1
        payloads = [item async for item in prompt]
        prompt_payloads.append(payloads[0]["message"]["content"])
        resumes.append(options.resume)
        if call_count == 1:
            yield _FakeSystemMessage("init", {"session_id": "sid-retry"})
            yield _FakeResultMessage(
                session_id="sid-retry",
                is_error=True,
                result="invalid_request_error: Could not process image",
            )
            return
        yield _FakeAssistantMessage([_FakeTextBlock("Recovered reply")])
        yield _FakeResultMessage(
            session_id="sid-retry",
            is_error=False,
            result="ok",
        )

    app.config._settings = FakeSettings()
    try:
        backend = ClaudeBackend()
        monkeypatch.setattr("app.agent.backends.claude_backend.query", _fake_query)
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.AssistantMessage",
            _FakeAssistantMessage,
        )
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.ResultMessage",
            _FakeResultMessage,
        )
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.SystemMessage",
            _FakeSystemMessage,
        )
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.TextBlock",
            _FakeTextBlock,
        )
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.build_system_prompt",
            lambda **kwargs: "prompt",
        )

        result = await backend.agent_turn(
            "Please help",
            attachments=[
                Attachment(
                    filename="photo.jpg",
                    mime_type="image/jpeg",
                    data=b"\xff\xd8",
                )
            ],
            on_event=_capture,
        )

        assert result.text == "Recovered reply"
        assert resumes == [None, "sid-retry"]
        first_content = prompt_payloads[0]
        second_content = prompt_payloads[1]
        assert any(block["type"] == "image" for block in first_content)
        assert not any(block["type"] == "image" for block in second_content)
        assert any("image upload fallback" in block["text"] for block in second_content)
        assert any(
            "photo.jpg (image/jpeg)" in block["text"] for block in second_content
        )
        assert any(event.kind == ExecutionEventKind.ERROR for event in events)
    finally:
        app.config._settings = old


@pytest.mark.asyncio
async def test_agent_turn_does_not_retry_unrelated_provider_errors(
    monkeypatch, workspace: Path, external_root: Path
):
    import app.config
    from app.agent.backends.claude_backend import ClaudeBackend

    old = app.config._settings

    @dataclass(frozen=True)
    class FakeSettings:
        workspace_dir: Path = workspace
        timezone: str = "Asia/Taipei"
        anthropic_api_key: str | None = None
        telegram_bot_token: str = "fake"
        allowed_telegram_user_id: int = 0
        slack_bot_token: str = "fake"
        slack_app_token: str = "fake"
        allowed_slack_user_id: str = "fake"
        agent_backend: str = "claude"
        chat_model: str = "claude-sonnet-4-5"
        background_model: str = "claude-sonnet-4-5"
        extra_writable_roots: tuple[Path, ...] = (external_root,)

    calls = 0

    async def _fake_query(*, prompt, options):
        nonlocal calls
        calls += 1
        if False:
            yield None
        raise RuntimeError("invalid_request_error: malformed tool schema")

    app.config._settings = FakeSettings()
    try:
        backend = ClaudeBackend()
        monkeypatch.setattr("app.agent.backends.claude_backend.query", _fake_query)
        monkeypatch.setattr(
            "app.agent.backends.claude_backend.build_system_prompt",
            lambda **kwargs: "prompt",
        )

        with pytest.raises(AgentError, match="malformed tool schema"):
            await backend.agent_turn(
                "Please help",
                attachments=[
                    Attachment(
                        filename="photo.jpg",
                        mime_type="image/jpeg",
                        data=b"\xff\xd8",
                    )
                ],
            )

        assert calls == 1
    finally:
        app.config._settings = old
