from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


@dataclass(frozen=True)
class Settings:
    # Anthropic (optional — if unset, SDK uses OAuth from ~/.claude/)
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY")
    )

    # Telegram (optional — omit to disable Telegram channel)
    telegram_bot_token: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN")
    )
    allowed_telegram_user_id: int | None = field(
        default_factory=lambda: (
            int(v) if (v := os.getenv("ALLOWED_TELEGRAM_USER_ID")) else None
        )
    )

    # Slack (optional — omit to disable Slack channel)
    slack_bot_token: str | None = field(
        default_factory=lambda: os.getenv("SLACK_BOT_TOKEN")
    )
    slack_app_token: str | None = field(
        default_factory=lambda: os.getenv("SLACK_APP_TOKEN")
    )
    allowed_slack_user_id: str | None = field(
        default_factory=lambda: os.getenv("ALLOWED_SLACK_USER_ID")
    )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.allowed_telegram_user_id)

    @property
    def slack_enabled(self) -> bool:
        return bool(
            self.slack_bot_token and self.slack_app_token and self.allowed_slack_user_id
        )

    # Paths
    workspace_dir: Path = field(
        default_factory=lambda: Path(os.getenv("WORKSPACE_DIR", "workspace")).resolve()
    )
    obsidian_vault_path: Path | None = field(
        default_factory=lambda: (
            Path(p).resolve() if (p := os.getenv("OBSIDIAN_VAULT_PATH")) else None
        )
    )
    # Timezone
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Taipei"))

    # Models
    agent_backend: str = field(
        default_factory=lambda: os.getenv("AGENT_BACKEND", "codex")
    )
    chat_model: str = field(default_factory=lambda: os.getenv("CHAT_MODEL", "gpt-5.4"))
    background_model: str = field(
        default_factory=lambda: os.getenv("BACKGROUND_MODEL", "gpt-5.4")
    )

    # Codex App Server
    codex_app_server_command: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            shlex.split(os.getenv("CODEX_APP_SERVER_COMMAND", "codex app-server"))
        )
    )
    codex_approval_policy: str = field(
        default_factory=lambda: os.getenv("CODEX_APPROVAL_POLICY", "never")
    )
    codex_sandbox_mode: str = field(
        default_factory=lambda: os.getenv("CODEX_SANDBOX_MODE", "workspace-write")
    )
    codex_rpc_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CODEX_RPC_TIMEOUT_SECONDS", "120"))
    )
    codex_rpc_stream_limit_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("CODEX_RPC_STREAM_LIMIT_BYTES", str(1024 * 1024))
        )
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


class _SettingsProxy:
    """Lazy proxy so `from app.config import settings` works without
    requiring env vars at import time."""

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings: Settings = _SettingsProxy()  # type: ignore[assignment]
