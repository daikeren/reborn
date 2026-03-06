from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@pytest.fixture()
def workspace(tmp_path: Path):
    """Patch settings to use a temp directory."""
    import app.config

    @dataclass(frozen=True)
    class FakeSettings:
        workspace_dir: Path = tmp_path
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
        obsidian_vault_path: Path | None = None
        extra_writable_roots: tuple[Path, ...] = ()
        codex_app_server_command: tuple[str, ...] = ("codex", "app-server")
        codex_approval_policy: str = "never"
        codex_sandbox_mode: str = "workspace-write"
        codex_rpc_timeout_seconds: float = 60.0
        codex_rpc_stream_limit_bytes: int = 1024 * 1024

    fake = FakeSettings()
    old = app.config._settings
    app.config._settings = fake
    yield tmp_path
    app.config._settings = old


@pytest.fixture()
def obsidian_vault(tmp_path: Path):
    """Create a temp vault with sample files for obsidian tool tests."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note1.md").write_text("# First Note\nHello world\n")
    (vault / "note2.md").write_text("# Second Note\nFoo bar baz\n")
    sub = vault / "projects"
    sub.mkdir()
    (sub / "project-a.md").write_text("# Project A\nSome project notes\n")
    # dotfile directory (should be hidden)
    dot = vault / ".obsidian"
    dot.mkdir()
    (dot / "config.json").write_text("{}")
    return vault
