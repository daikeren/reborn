from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


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
        assert captured["add_dirs"] == [str(external_root)]
    finally:
        app.config._settings = old
