from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

DEFAULT_REPO_URL = "https://github.com/daikeren/reborn.git"
DEFAULT_WORKSPACE_DIR = "workspace"
DEFAULT_INSTALL_DIR = "~/Applications/reborn"
DEFAULT_JOB_FILES = ("heartbeat.md", "morning_brief.md", "weekly_review.md")
MANAGED_ENV_KEYS = (
    "AGENT_BACKEND",
    "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_TELEGRAM_USER_ID",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "ALLOWED_SLACK_USER_ID",
    "WORKSPACE_DIR",
    "TIMEZONE",
)

SOUL_TEMPLATE = """# {assistant_name} — Your Personal AI Assistant

You are {assistant_name}, {owner_name}'s personal AI assistant. Use {primary_language} by default unless {owner_name} clearly switches languages.

## Personality

- Direct and concise — no filler, no pleasantries unless initiated
- Proactive — if you notice something relevant, mention it
- Honest — say "I don't know" rather than guess
- Context-aware — use memory and recent context to give relevant answers

## Values

- Respect time — keep responses short unless asked for detail
- Protect before acting — never execute destructive operations without confirmation
- Remember selectively — only persist information explicitly asked to remember
- Have opinions — can disagree when there's good reason to
- Resourceful — try to figure things out before asking for help

## Boundaries

- Strictly protect personal information
- Always get permission before external actions (sending messages, public posts)
- Do not impersonate {owner_name} in group conversations

## Autonomy

Safe to do freely: read files, search, local organization, web search
Requires confirmation: send messages, public posts, delete files, any action leaving the system

## Group Chat (Slack)

- Respond when @mentioned
- Only speak up when you can provide genuinely valuable information
- Otherwise stay silent — don't dominate conversations

## Heartbeat

- Quiet hours: 23:00–08:00, no messages unless urgent
- No message when there's nothing to report (use suppress token)

## General

- When searching for information, prefer web search for current events
- Today's date is always available in your system prompt context

## Memory

You have three memory tools:

- **memory_write**: Append to today's daily log. Use ONLY when explicitly asked to remember something, or when a clear fact/preference is stated.
- **memory_search**: Search past memory logs and core memory. Use when past context is referenced, or when historical context would help answer a question.
- **memory_update_core**: Update a section in core memory (MEMORY.md). Use when information is stable and permanent — not just daily context.

**Important**: MEMORY.md and today/yesterday logs are already loaded in your system prompt. You do not need to search for recent items — just read the context above.

## Optional Tools

- Use the `google-workspace` skill only when gogcli is installed and authenticated.
- Use Obsidian tools only when an Obsidian vault path is configured.
"""

MEMORY_TEMPLATE = """## Preferences
- Primary language: {primary_language}
- Communication style preferences
- Tools and workflows you use daily

## Projects
- Active projects with brief descriptions

## People
- Key contacts with roles and context

## Facts
- Important URLs and paths
- Environment defaults and recurring constraints

## Top of Mind
- Current priorities and focus areas
"""

HEARTBEAT_TEMPLATE = """---
schedule: "*/30 * * * *"
tools:
  - WebSearch
  - mcp__memory__memory_search
max_turns: 8
suppress_token: HEARTBEAT_OK
---
Review recent memory and anything time-sensitive that deserves attention within the next 2 hours.

Only alert me about items that are:
- overdue
- due today
- urgent within the next 2 hours

If there is nothing clearly urgent, respond with ONLY: HEARTBEAT_OK

Do NOT output process narration.
Do NOT write to memory.
"""

MORNING_BRIEF_TEMPLATE = """---
schedule: "0 7 * * *"
tools:
  - WebSearch
  - mcp__memory__memory_search
max_turns: 10
---
Prepare my daily brief:

1. Summarize anything important from memory that is relevant today.
2. Highlight deadlines, follow-ups, or open loops due today.
3. Check the weather forecast for the day.
4. End with a short actionable priority list.

Do NOT output process narration.
Do NOT write to memory.
"""

WEEKLY_REVIEW_TEMPLATE = """---
schedule: "0 18 * * 5"
tools:
  - mcp__memory__memory_search
max_turns: 10
---
Prepare my weekly review:

1. Search memory for this week's key activities, decisions, and learnings.
2. Summarize accomplishments, open items, and priorities for next week.

Start your response with "Weekly Review".
Do NOT output process narration.
Do NOT write to memory.
"""

JOB_TEMPLATE_MAP = {
    "heartbeat.md": HEARTBEAT_TEMPLATE,
    "morning_brief.md": MORNING_BRIEF_TEMPLATE,
    "weekly_review.md": WEEKLY_REVIEW_TEMPLATE,
}


@dataclass
class ChannelStatus:
    configured: bool
    missing_keys: list[str] = field(default_factory=list)


@dataclass
class BackendStatus:
    selected: str | None
    ready: bool
    missing: list[str] = field(default_factory=list)


@dataclass
class WorkspaceStatus:
    workspace_dir: str
    soul_exists: bool
    memory_exists: bool
    default_job_files: dict[str, bool]


@dataclass
class SetupInspection:
    repo_root: str
    env_file_exists: bool
    backend: BackendStatus
    channels: dict[str, ChannelStatus]
    workspace: WorkspaceStatus
    optional_integrations: dict[str, Any]
    blocking_problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SetupAnswers:
    assistant_name: str
    owner_name: str
    primary_language: str
    timezone: str
    backend: str
    workspace_dir: str = DEFAULT_WORKSPACE_DIR
    anthropic_api_key: str | None = None
    telegram_bot_token: str | None = None
    allowed_telegram_user_id: str | None = None
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    allowed_slack_user_id: str | None = None
    overwrite_env: bool = True
    overwrite_soul: bool = False
    overwrite_memory: bool = False
    overwrite_prompts: bool = False

    @classmethod
    def from_json_file(cls, path: Path) -> "SetupAnswers":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)


def repo_root_from(start: Path | None = None) -> Path:
    return (start or Path.cwd()).resolve()


def _env_values(repo_root: Path) -> dict[str, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return {}
    return {k: v for k, v in dotenv_values(env_path).items() if v is not None}


def _workspace_dir(repo_root: Path, env: dict[str, str]) -> Path:
    raw = env.get("WORKSPACE_DIR", DEFAULT_WORKSPACE_DIR)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _codex_auth_ready() -> bool:
    codex_home_raw = os.getenv("CODEX_HOME")
    codex_home = (
        Path(codex_home_raw).expanduser() if codex_home_raw else Path.home() / ".codex"
    )
    return (codex_home / "auth.json").exists()


def _claude_auth_ready() -> bool:
    if os.getenv("ANTHROPIC_API_KEY"):
        return True
    return (Path.home() / ".claude").exists()


def _channel_status(env: dict[str, str], prefix: str) -> ChannelStatus:
    if prefix == "telegram":
        keys = ("TELEGRAM_BOT_TOKEN", "ALLOWED_TELEGRAM_USER_ID")
    else:
        keys = ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "ALLOWED_SLACK_USER_ID")
    missing = [key for key in keys if not env.get(key)]
    return ChannelStatus(configured=not missing, missing_keys=missing)


def inspect_setup(repo_root: Path | None = None) -> SetupInspection:
    root = repo_root_from(repo_root)
    env = _env_values(root)
    workspace_dir = _workspace_dir(root, env)
    backend_name = env.get("AGENT_BACKEND")
    backend_missing: list[str] = []
    backend_ready = False

    if backend_name == "codex":
        if not shutil.which("codex"):
            backend_missing.append("codex CLI is not installed or not on PATH")
        if not _codex_auth_ready():
            backend_missing.append("codex login has not been completed")
        backend_ready = not backend_missing
    elif backend_name == "claude":
        if not env.get("ANTHROPIC_API_KEY") and not _claude_auth_ready():
            backend_missing.append("Anthropic API key or Claude login was not detected")
        backend_ready = not backend_missing
    else:
        backend_missing.append("AGENT_BACKEND is not configured")

    telegram = _channel_status(env, "telegram")
    slack = _channel_status(env, "slack")
    default_job_status = {
        name: (
            (workspace_dir / "jobs" / name).exists()
            or (workspace_dir / "prompts" / name).exists()
        )
        for name in DEFAULT_JOB_FILES
    }

    inspection = SetupInspection(
        repo_root=str(root),
        env_file_exists=(root / ".env").exists(),
        backend=BackendStatus(
            selected=backend_name,
            ready=backend_ready,
            missing=backend_missing,
        ),
        channels={"telegram": telegram, "slack": slack},
        workspace=WorkspaceStatus(
            workspace_dir=str(workspace_dir),
            soul_exists=(workspace_dir / "SOUL.md").exists(),
            memory_exists=(workspace_dir / "MEMORY.md").exists(),
            default_job_files=default_job_status,
        ),
        optional_integrations={
            "gog_installed": bool(shutil.which("gog")),
            "obsidian_vault_configured": bool(env.get("OBSIDIAN_VAULT_PATH")),
        },
    )

    if not inspection.env_file_exists:
        inspection.blocking_problems.append(".env is missing")
    if inspection.backend.missing:
        inspection.blocking_problems.extend(inspection.backend.missing)
    if (
        not telegram.configured
        and telegram.missing_keys
        and any(
            env.get(key) for key in ("TELEGRAM_BOT_TOKEN", "ALLOWED_TELEGRAM_USER_ID")
        )
    ):
        inspection.blocking_problems.append(
            "Telegram configuration is incomplete: " + ", ".join(telegram.missing_keys)
        )
    if (
        not slack.configured
        and slack.missing_keys
        and any(
            env.get(key)
            for key in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "ALLOWED_SLACK_USER_ID")
        )
    ):
        inspection.blocking_problems.append(
            "Slack configuration is incomplete: " + ", ".join(slack.missing_keys)
        )
    if not (telegram.configured or slack.configured):
        inspection.blocking_problems.append(
            "At least one channel must be fully configured"
        )
    if not inspection.workspace.soul_exists:
        inspection.blocking_problems.append(
            f"Missing {Path(inspection.workspace.workspace_dir) / 'SOUL.md'}"
        )
    if not inspection.workspace.memory_exists:
        inspection.blocking_problems.append(
            f"Missing {Path(inspection.workspace.workspace_dir) / 'MEMORY.md'}"
        )

    if not inspection.optional_integrations["gog_installed"]:
        inspection.warnings.append("Optional integration unavailable: gogcli not found")
    if not inspection.optional_integrations["obsidian_vault_configured"]:
        inspection.warnings.append(
            "Optional integration unavailable: OBSIDIAN_VAULT_PATH not configured"
        )
    return inspection


def _managed_env_values(answers: SetupAnswers) -> dict[str, str]:
    values = {
        "AGENT_BACKEND": answers.backend,
        "WORKSPACE_DIR": answers.workspace_dir,
        "TIMEZONE": answers.timezone,
    }
    if answers.backend == "claude" and answers.anthropic_api_key:
        values["ANTHROPIC_API_KEY"] = answers.anthropic_api_key
    if answers.telegram_bot_token:
        values["TELEGRAM_BOT_TOKEN"] = answers.telegram_bot_token
    if answers.allowed_telegram_user_id:
        values["ALLOWED_TELEGRAM_USER_ID"] = answers.allowed_telegram_user_id
    if answers.slack_bot_token:
        values["SLACK_BOT_TOKEN"] = answers.slack_bot_token
    if answers.slack_app_token:
        values["SLACK_APP_TOKEN"] = answers.slack_app_token
    if answers.allowed_slack_user_id:
        values["ALLOWED_SLACK_USER_ID"] = answers.allowed_slack_user_id
    return values


def _format_env_value(key: str, value: str) -> str:
    if re.search(r"\s", value):
        encoded = json.dumps(value)
        return f"{key}={encoded}"
    return f"{key}={value}"


def _merge_env_text(
    base_text: str, managed: dict[str, str]
) -> tuple[str, list[str], list[str]]:
    lines = base_text.splitlines()
    seen: set[str] = set()
    added: list[str] = []
    updated: list[str] = []
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=")
    rendered: list[str] = []

    for line in lines:
        match = pattern.match(line)
        if not match:
            rendered.append(line)
            continue
        key = match.group(1)
        if key in managed:
            rendered.append(_format_env_value(key, managed[key]))
            seen.add(key)
            updated.append(key)
        else:
            rendered.append(line)

    missing = [key for key in managed if key not in seen]
    if missing:
        if rendered and rendered[-1] != "":
            rendered.append("")
        rendered.append("# Active settings")
        for key in missing:
            rendered.append(_format_env_value(key, managed[key]))
            added.append(key)

    text = "\n".join(rendered).rstrip() + "\n"
    return text, added, updated


def _write_file(path: Path, content: str, *, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _job_content(name: str) -> str:
    return JOB_TEMPLATE_MAP[name]


def apply_setup(
    answers: SetupAnswers,
    repo_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = repo_root_from(repo_root)
    workspace_dir = _workspace_dir(root, {"WORKSPACE_DIR": answers.workspace_dir})
    env_path = root / ".env"
    example_path = root / ".env.example"
    base_env_text = (
        env_path.read_text(encoding="utf-8")
        if env_path.exists()
        else example_path.read_text(encoding="utf-8")
    )
    env_text, added_keys, updated_keys = _merge_env_text(
        base_env_text, _managed_env_values(answers)
    )

    soul_path = workspace_dir / "SOUL.md"
    memory_path = workspace_dir / "MEMORY.md"
    jobs_dir = workspace_dir / "jobs"

    planned_files: list[str] = []
    if not env_path.exists() or answers.overwrite_env:
        planned_files.append(str(env_path))
    if not soul_path.exists() or answers.overwrite_soul:
        planned_files.append(str(soul_path))
    if not memory_path.exists() or answers.overwrite_memory:
        planned_files.append(str(memory_path))
    for name in DEFAULT_JOB_FILES:
        path = jobs_dir / name
        if not path.exists() or answers.overwrite_prompts:
            planned_files.append(str(path))

    if dry_run:
        return {
            "dry_run": True,
            "files_written": planned_files,
            "keys_added": added_keys,
            "keys_updated": updated_keys,
        }

    files_written: list[str] = []
    if not env_path.exists() or answers.overwrite_env:
        env_path.write_text(env_text, encoding="utf-8")
        files_written.append(str(env_path))
    if _write_file(
        soul_path,
        SOUL_TEMPLATE.format(
            assistant_name=answers.assistant_name,
            owner_name=answers.owner_name,
            primary_language=answers.primary_language,
        ),
        overwrite=answers.overwrite_soul,
    ):
        files_written.append(str(soul_path))
    if _write_file(
        memory_path,
        MEMORY_TEMPLATE.format(primary_language=answers.primary_language),
        overwrite=answers.overwrite_memory,
    ):
        files_written.append(str(memory_path))
    for name in DEFAULT_JOB_FILES:
        path = jobs_dir / name
        if _write_file(path, _job_content(name), overwrite=answers.overwrite_prompts):
            files_written.append(str(path))

    return {
        "dry_run": False,
        "files_written": files_written,
        "keys_added": added_keys,
        "keys_updated": updated_keys,
    }


def verify_setup(repo_root: Path | None = None) -> dict[str, Any]:
    inspection = inspect_setup(repo_root)
    errors = inspection.blocking_problems
    next_steps: list[str] = []
    if errors:
        if any("codex" in err for err in errors):
            next_steps.append("Run `codex login` and re-run verify.")
        if any("Anthropic" in err or "Claude" in err for err in errors):
            next_steps.append(
                "Set ANTHROPIC_API_KEY or run `claude login`, then re-run verify."
            )
        if any("channel" in err.lower() for err in errors):
            next_steps.append("Fill in one full channel configuration in `.env`.")
        if any("SOUL.md" in err or "MEMORY.md" in err for err in errors):
            next_steps.append("Run setup apply to create the missing workspace files.")
    else:
        next_steps.extend(
            [
                "Run `uv run uvicorn app.main:app --reload`.",
                "Optionally check `/health`, `/history`, and `/monitor` once the app is up.",
            ]
        )
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": inspection.warnings,
        "next_steps": next_steps,
        "inspection": inspection.to_dict(),
    }


def json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def emit_json(data: Any) -> None:
    sys.stdout.write(json_dumps(data))
