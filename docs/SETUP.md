# Setup Guide

This guide walks you through setting up your own instance of Reborn after cloning the repo.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- One of the following LLM backends:
  - **Codex** (default): Install [Codex CLI](https://github.com/openai/codex) and run `codex login`
  - **Claude**: Have an Anthropic API key, or authenticate via `claude login` (OAuth stored in `~/.claude/`)

## Step 1: Install Dependencies

```bash
uv sync --dev
```

## Step 2: Create Your Environment File

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

### Required: Telegram

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram to create a new bot
2. Copy the bot token to `TELEGRAM_BOT_TOKEN`
3. Find your Telegram user ID (you can use [@userinfobot](https://t.me/userinfobot)) and set `ALLOWED_TELEGRAM_USER_ID`

### Required: Slack

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** and generate an app-level token (`xapp-...`) -> `SLACK_APP_TOKEN`
3. Under **OAuth & Permissions**, add these bot scopes:
   - `chat:write`, `reactions:write`, `channels:history`, `groups:history`, `im:history`, `files:read`
4. Install the app to your workspace and copy the bot token (`xoxb-...`) -> `SLACK_BOT_TOKEN`
5. Find your Slack user ID (Profile -> three dots -> Copy member ID) -> `ALLOWED_SLACK_USER_ID`

### Optional: Backend Selection

```bash
# Default is codex. Switch to claude if preferred:
AGENT_BACKEND=claude
ANTHROPIC_API_KEY=sk-ant-...

# Or stick with codex (default):
AGENT_BACKEND=codex
```

## Step 3: Set Up Your Workspace

The `workspace/` directory contains your assistant's personality, memory, and prompts. The repo provides `.example` templates — you need to create your own versions.

### 3a. Create SOUL.md (Required)

This defines who your assistant is.

```bash
cp workspace/SOUL.md.example workspace/SOUL.md
```

Edit `workspace/SOUL.md` and customize:

- **Name**: Replace `[Name]` with whatever you want to call your assistant
- **Owner**: Replace `[Owner]` with your name
- **Personality & Values**: Adjust to match your communication style
- **Boundaries & Autonomy**: Define what the assistant can do freely vs. needs permission
- **Quiet hours**: Change `23:00-08:00` to match your schedule
- **Tool sections**: Remove sections for tools you don't use (Google Workspace, Obsidian, etc.)

### 3b. Create MEMORY.md (Required)

This is your assistant's long-term memory. It starts mostly empty and grows over time.

```bash
cp workspace/MEMORY.md.example workspace/MEMORY.md
```

Fill in the sections that apply to you:

- **Preferences**: Your language, communication style
- **Projects**: What you're working on
- **People**: Key contacts your assistant should know about
- **Facts**: Your tech stack, company info, important URLs

The assistant will update this file over time as it learns about you.

### 3c. Customize Scheduled Prompts (Optional)

The `workspace/prompts/` directory contains prompts for proactive scheduled jobs:

| File | Schedule | Purpose |
|---|---|---|
| `heartbeat.md` | Every 30 min | Check calendar for upcoming events, alert if urgent |
| `morning_brief.md` | Daily 07:00 | Daily briefing with calendar, tasks, weather |
| `weekly_review.md` | Friday 18:00 | Weekly summary and review |

Each prompt file supports YAML frontmatter:

```yaml
---
tools:
  - WebSearch
  - Bash
max_turns: 10
suppress_token: HEARTBEAT_OK   # if output matches this, don't send the message
---
Your prompt text here...
```

Edit these to match your workflow. For example:
- Remove `gog calendar events` commands if you don't use Google Workspace
- Change the morning brief to include different data sources
- Adjust the weekly review to match your review process

### 3d. Configure Skills (Optional)

Skills live in `workspace/skills/*/SKILL.md`. The included skills are:

| Skill | Requires |
|---|---|
| `google-workspace` | [gogcli](https://github.com/steipete/gogcli) installed + `gog auth add` |
| `speedcaster` | YouTube transcript script |
| `obsidian-markdown` | An Obsidian vault (`OBSIDIAN_VAULT_PATH` in `.env`) |
| `obsidian-bases` | Same as above |
| `charlie-munger-mental-models` | Nothing extra |
| `web-researcher` | Nothing extra |

Remove skill directories you don't need. They're auto-loaded at startup.

## Step 4: Configure Timezone

Default is `Asia/Taipei`. Change it in `.env` if you're in a different timezone:

```bash
TIMEZONE=America/New_York
```

This affects:
- Scheduled job cron triggers (heartbeat, morning brief, weekly review)
- Session daily reset time (04:00 in your timezone)

## Step 5: Run

```bash
uv run uvicorn app.main:app --reload
```

On startup you should see logs for:
- Session store initialized
- Telegram polling started
- Slack Socket Mode started
- Scheduler startup completed

### Verify

- **Health check**: `curl http://127.0.0.1:8000/health`
- **Session history UI**: Open `http://127.0.0.1:8000/history` in a browser
- **Monitoring**: Open `http://127.0.0.1:8000/monitor`
- **Chat**: Send a message to your Telegram bot or mention it in Slack

## Step 6: Optional Integrations

### Google Workspace

```bash
# Install gogcli
brew install steipete/formulae/gogcli   # or build from source

# Authenticate
gog auth add

# Set in .env
GOG_ACCOUNT=your-email@gmail.com
```

### Obsidian Vault

```bash
# Set in .env — enables obsidian_* tools and adds path to sandbox roots
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

## Troubleshooting

### "Missing required environment variable"
You're missing a required token in `.env`. Check `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_ID`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `ALLOWED_SLACK_USER_ID`.

### "gogcli (gog) not found on PATH"
This is a warning, not an error. Google Workspace features won't work, but the service will still start.

### Scheduler jobs produce no output
Check that your prompts reference tools you actually have. If you don't have `gogcli`, remove the `gog calendar events` commands from `heartbeat.md` and `morning_brief.md`.

### Bot doesn't respond
- Verify your user ID matches the `ALLOWED_*_USER_ID` in `.env`
- Check the service logs for auth rejection messages
