# Setup Guide

This guide covers the manual fallback path for setting up your own instance of Reborn after cloning the repo.

## Recommended Path

If you are using Codex or Claude Code, install the bootstrap skill first:

```bash
uv run python scripts/install_setup_skill.py
```

Without a local clone, you can fetch the installer directly:

```bash
curl -fsSL https://raw.githubusercontent.com/daikeren/reborn/main/scripts/install_setup_skill.py | python3 -
```

Then invoke `Reborn Setup` inside your coding agent. The skill will:

- clone Reborn into a directory you choose
- install dependencies with `uv sync --dev`
- inspect missing setup state
- collect your setup answers
- apply `.env` and workspace files
- verify readiness

## Prerequisites

- Python >= 3.10
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

Edit `.env` and configure **at least one channel** (Telegram or Slack, or both):

### Telegram (optional)

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram to create a new bot
2. Copy the bot token to `TELEGRAM_BOT_TOKEN`
3. Find your Telegram user ID (you can use [@userinfobot](https://t.me/userinfobot)) and set `ALLOWED_TELEGRAM_USER_ID`

### Slack (optional)

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** and generate an app-level token (`xapp-...`) -> `SLACK_APP_TOKEN`
3. Under **OAuth & Permissions**, add these bot scopes:
   - `chat:write`, `reactions:write`, `channels:history`, `groups:history`, `im:history`, `files:read`
4. Install the app to your workspace and copy the bot token (`xoxb-...`) -> `SLACK_BOT_TOKEN`
5. Find your Slack user ID (Profile -> three dots -> Copy member ID) -> `ALLOWED_SLACK_USER_ID`

> **Note**: Scheduled jobs (heartbeat, morning brief, weekly review) are delivered via Telegram. If you only enable Slack, the scheduler will be skipped.

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
- **Optional tools**: Add integrations only if you actually configure them

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

### 3c. Customize Scheduled Jobs (Optional)

The `workspace/jobs/` directory contains proactive scheduled job definitions:

| File | Schedule | Purpose |
|---|---|---|
| `heartbeat.md` | Every 30 min | Alert on anything urgent |
| `morning_brief.md` | Daily 07:00 | Daily briefing and priorities |
| `weekly_review.md` | Friday 18:00 | Weekly summary and review |

Each job definition file supports YAML frontmatter:

```yaml
---
schedule: "*/30 * * * *"
tools:
  - WebSearch
  - Bash
max_turns: 10
suppress_token: HEARTBEAT_OK   # if output matches this, don't send the message
---
Job instructions here...
```

Edit these to match your workflow. For example:
- Add calendar checks if you do use Google Workspace
- Add Obsidian search if you have an Obsidian vault
- Adjust the weekly review to match your review process

### 3d. Configure Skills (Optional)

Skills live in `workspace/skills/*/SKILL.md`. The included skills are:

| Skill | Requires |
|---|---|
| `google-workspace` | [gogcli](https://github.com/steipete/gogcli) installed + `gog auth add` |
| `speedcaster` | YouTube transcript script |
| `obsidian-markdown` | An Obsidian vault included in `EXTRA_WRITABLE_ROOTS` |
| `obsidian-bases` | Same as above |
| `charlie-munger-mental-models` | Nothing extra |
| `web-researcher` | Nothing extra |

Remove skill directories you don't need. Skills with unmet prerequisites remain on disk but are not exposed at runtime.

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
# Set in .env — adds external writable roots for both Codex and Claude backends
EXTRA_WRITABLE_ROOTS=/path/to/your/vault

# Deprecated compatibility alias
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

## Troubleshooting

### "At least one channel must be configured"
You need to set up either Telegram or Slack (or both) in `.env`. See Step 2 above.

### Scheduler jobs produce no output
Check that your prompts reference tools you actually have and that the prompt still contains actionable instructions for your workflow.

### Bot doesn't respond
- Verify your user ID matches the `ALLOWED_*_USER_ID` in `.env`
- Check the service logs for auth rejection messages
