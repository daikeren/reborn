# Reborn

Reborn is a personal AI assistant service that integrates Telegram and Slack, with support for proactive scheduled reminders, persistent conversation sessions, memory (MCP), and extensible skills.

## Key Features

- Dual-channel chat
  - Telegram: long polling, with `/new` support to reset the session.
  - Slack: Socket Mode, with thread-based conversation continuity.
- Streaming reply experience
  - Sends an initial `👀` reaction, then continuously updates the reply content.
  - Telegram shows a typing indicator.
- Session management (SQLite)
  - Telegram sessions support daily reset (default `04:00`) and idle reset (after 4 hours).
  - Slack keeps context by `channel + thread`.
  - Event deduplication with a 5-minute TTL.
- Proactive scheduling (APScheduler)
  - `heartbeat`: every 30 minutes.
  - `morning_brief`: daily at `07:00`.
  - `weekly_review`: every Friday at `18:00`.
- MCP capabilities
  - Built-in memory MCP for writing, searching, and updating `workspace/MEMORY.md`.
  - Optional Google Workspace integration via `gogcli` for Calendar, Gmail, Drive, and Tasks.
- Switchable model backends
  - `codex` (default)
  - `claude`
- Health check
  - `GET /health` returns `status`, `active_sessions`, and `max_message_count`.

## Technical Architecture

- API/Lifecycle: `FastAPI` (`app/main.py`)
- Channels: `python-telegram-bot` + `slack-bolt`
- Scheduling: `APScheduler`
- Session Store: `SQLite` (WAL)
- Agent Runtime:
  - Backend factory (`codex` / `claude`)
  - System prompt assembly from `workspace/SOUL.md`, `workspace/MEMORY.md`, recent two-day memory logs, and loaded skills
- MCP:
  - `app.mcp.server` exposes memory tools
  - Google Workspace can be attached through the `gogcli` skill

## Quick Start

### 1) Requirements

- Python `>=3.10`
- `uv`
- If using `AGENT_BACKEND=codex`: install and log in to the Codex CLI with `codex login`
- If using Google Workspace: install [gogcli](https://github.com/steipete/gogcli) and run `gog auth add`

### 2) Install dependencies

```bash
uv sync --dev
```

### 2.1) Install git hooks

```bash
uv run prek install --install-hooks
```

Run all hooks on demand:

```bash
uv run prek run --all-files
```

The repo keeps its hook definitions in `.pre-commit-config.yaml`, which `prek` can consume directly.
At the moment, the `ty` hook is scoped to `app/` so commits are gated on application code typing without being blocked by existing test-only typing debt.

### 3) Configure environment variables

```bash
cp .env.example .env
```

Enable at least one channel, either Telegram or Slack:

- Telegram: set `TELEGRAM_BOT_TOKEN` + `ALLOWED_TELEGRAM_USER_ID`
- Slack: set `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` + `ALLOWED_SLACK_USER_ID`

### 4) Start the service

```bash
uv run uvicorn app.main:app --reload
```

At startup, depending on your configuration, the service will:

- start Telegram polling (requires Telegram token)
- start Slack Socket Mode (requires Slack token)
- start the scheduler (requires the Telegram channel for scheduled message delivery)

After startup, you can open these pages in a browser:

- `http://127.0.0.1:8000/history` for the session list with pagination
- open any session to view its detailed message history

## Common Commands

```bash
# Run the full test suite
uv run pytest

# Run formatting + type hooks across the repo
uv run prek run --all-files

# Run a focused subset
uv run pytest tests/test_scheduler_jobs.py -k cadence

# List recent sessions (including session key / sdk_session_id / counts)
uv run python scripts/session_history.py --list-sessions --limit 50

# Inspect message history for a specific session (user/assistant content)
uv run python scripts/session_history.py --session-key "telegram:dm" --limit 200
```

## Important Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `AGENT_BACKEND` | `codex` or `claude` | No (default: `codex`) |
| `CHAT_MODEL` | Model for real-time chat | No |
| `BACKGROUND_MODEL` | Model for scheduled jobs | No |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | At least one channel must be enabled |
| `ALLOWED_TELEGRAM_USER_ID` | Allowed Telegram user ID | Same as above |
| `SLACK_BOT_TOKEN` | Slack bot token | Same as above |
| `SLACK_APP_TOKEN` | Slack app token for Socket Mode | Same as above |
| `ALLOWED_SLACK_USER_ID` | Allowed Slack user ID | Same as above |
| `WORKSPACE_DIR` | Workspace path | No (default: `workspace`) |
| `TIMEZONE` | Time zone for scheduling and session resets | No (default: `Asia/Taipei`) |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault path (must be writable within sandbox roots) | No |
| `GOG_ACCOUNT` | Google account for `gogcli` (requires `gog auth add` first) | No |
| `CODEX_APP_SERVER_COMMAND` | Command used to start the Codex app server | No |
| `CODEX_APPROVAL_POLICY` | Codex approval policy | No |
| `CODEX_SANDBOX_MODE` | Codex sandbox mode | No |
| `CODEX_RPC_TIMEOUT_SECONDS` | Codex RPC timeout | No |
| `CODEX_RPC_STREAM_LIMIT_BYTES` | Per-line stdout/stderr limit for Codex RPC, in bytes | No |
| `ANTHROPIC_API_KEY` | API key for the Claude backend (optional; falls back to `~/.claude` OAuth if unset) | No |

## Workspace Conventions

`WORKSPACE_DIR` (default: `workspace/`) is expected to contain:

- `SOUL.md`: identity, behavioral rules, and tool guidance
- `MEMORY.md`: factual memory maintained by the assistant, such as preferences, people, and company information
- `memory/YYYY-MM-DD.md`: daily records
- `prompts/heartbeat.md`
- `prompts/morning_brief.md`
- `prompts/weekly_review.md`
- `skills/*/SKILL.md`: loadable skills

## Prompt and Schedule Customization

Scheduled prompt files support YAML frontmatter:

- `tools`: allowed tool list
- `max_turns`: maximum number of turns
- `suppress_token`: if the model outputs this token, no message is sent; commonly used when `heartbeat` has nothing to report

See `workspace/prompts/*.md` for examples.

## Project Structure

```text
app/
  main.py                # FastAPI lifecycle, channels + scheduler startup
  channels/              # Telegram / Slack handlers
  agent/                 # runtime, backend, prompt, skills, tools
  scheduler/             # jobs, prompt loader, delivery, runner
  sessions/              # SQLite session store + manager
  mcp/                   # memory MCP server/tools
tests/                   # pytest tests
workspace/               # prompts, skills, memory, soul
```

## Security Notes

- Do not commit any secrets.
- `.env`, `client_secret*.json`, and runtime SQLite/memory artifacts are already ignored.
