# Reborn 

Reborn 是一個以 FastAPI 為核心的個人 AI 助理服務，整合 Telegram 與 Slack，支援主動排程提醒、持久化對話 session、記憶（MCP）與可擴充 skills。

## 主要功能

- 雙通道聊天
  - Telegram：long polling，支援 `/new` 重置 session。
  - Slack：Socket Mode，支援 thread 內對話延續。
- 串流回覆體驗
  - 先回 👀 reaction，再持續更新回覆內容。
  - Telegram 會顯示 typing indicator。
- Session 管理（SQLite）
  - Telegram session 具備每日重置（預設 04:00）與閒置重置（4 小時）。
  - Slack 以 `channel + thread` 維持上下文。
  - 事件去重（5 分鐘 TTL）。
- 主動排程（APScheduler）
  - `heartbeat`：每 30 分鐘。
  - `morning_brief`：每日 07:00。
  - `weekly_review`：每週五 18:00。
- MCP 能力
  - 內建 memory MCP（寫入、搜尋、更新 `workspace/MEMORY.md`）。
  - 可選 Google Workspace（透過 gogcli 讀取行事曆、Gmail、Drive、Tasks）。
- 可切換模型 backend
  - `codex`（預設）
  - `claude`
- Health Check
  - `GET /health` 回傳 `status`, `active_sessions`, `max_message_count`。

## 技術架構

- API/Lifecycle：`FastAPI`（`app/main.py`）
- Channels：`python-telegram-bot` + `slack-bolt`
- Scheduling：`APScheduler`
- Session Store：`SQLite`（WAL）
- Agent Runtime：
  - Backend factory (`codex` / `claude`)
  - System prompt 組裝（`workspace/SOUL.md`, `workspace/MEMORY.md`, 近兩日 memory log, skills）
- MCP：
  - `app.mcp.server` 提供 memory tools
  - 可掛 Google Workspace（gogcli skill）

## 快速開始

### 1) 需求

- Python `>=3.12`
- `uv`
- 若使用 `AGENT_BACKEND=codex`：需安裝並登入 Codex CLI（`codex login`）
- 若使用 Google Workspace：需安裝 [gogcli](https://github.com/steipete/gogcli) 並執行 `gog auth add`

### 2) 安裝依賴

```bash
uv sync --dev
```

### 3) 設定環境變數

```bash
cp .env.example .env
```

至少要填入：

- `TELEGRAM_BOT_TOKEN`
- `ALLOWED_TELEGRAM_USER_ID`
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `ALLOWED_SLACK_USER_ID`

### 4) 啟動服務

```bash
uv run uvicorn app.main:app --reload
```

啟動時會同時：

- 啟動 Telegram polling
- 啟動 Slack Socket Mode
- 啟動 scheduler（3 個排程任務）

啟動後可在瀏覽器開啟：

- `http://127.0.0.1:8000/history`（session list，含 pagination）
- 點任一 session 進入 detail page 查看 message history

## 常用指令

```bash
# 全部測試
uv run pytest

# 跑指定測試
uv run pytest tests/test_scheduler_jobs.py -k cadence

# 列出最近 sessions（含 session key / sdk_session_id / 計數）
uv run python scripts/session_history.py --list-sessions --limit 50

# 查看某個 session 的歷史訊息（user/assistant 內文）
uv run python scripts/session_history.py --session-key "telegram:dm" --limit 200
```

## 環境變數重點

| 變數 | 用途 | 必填 |
|---|---|---|
| `AGENT_BACKEND` | `codex` 或 `claude` | 否（預設 `codex`） |
| `CHAT_MODEL` | 即時對話模型 | 否 |
| `BACKGROUND_MODEL` | 排程任務模型 | 否 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token | 是 |
| `ALLOWED_TELEGRAM_USER_ID` | 允許的 Telegram user id | 是 |
| `SLACK_BOT_TOKEN` | Slack Bot token | 是 |
| `SLACK_APP_TOKEN` | Slack App token（Socket Mode） | 是 |
| `ALLOWED_SLACK_USER_ID` | 允許的 Slack user id | 是 |
| `WORKSPACE_DIR` | workspace 路徑 | 否（預設 `workspace`） |
| `TIMEZONE` | 排程與 session reset 時區 | 否（預設 `Asia/Taipei`） |
| `OBSIDIAN_VAULT_PATH` | Obsidian vault 路徑（可寫入 sandbox roots） | 否 |
| `GOG_ACCOUNT` | gogcli Google 帳號（需先 `gog auth add`） | 否 |
| `CODEX_APP_SERVER_COMMAND` | 啟動 codex app-server 指令 | 否 |
| `CODEX_APPROVAL_POLICY` | Codex approval policy | 否 |
| `CODEX_SANDBOX_MODE` | Codex sandbox 模式 | 否 |
| `CODEX_RPC_TIMEOUT_SECONDS` | Codex RPC timeout | 否 |
| `CODEX_RPC_STREAM_LIMIT_BYTES` | Codex RPC stdout/stderr 單行上限（bytes） | 否 |
| `ANTHROPIC_API_KEY` | Claude backend API key（可選，未設則走 `~/.claude` OAuth） | 否 |

## Workspace 約定

`WORKSPACE_DIR`（預設 `workspace/`）建議包含：

- `SOUL.md`：身份、行為準則、工具指南（你寫給 Dio 的一切）
- `MEMORY.md`：事實記憶（Dio 自己維護的偏好、人物、公司資訊）
- `memory/YYYY-MM-DD.md`：每日記錄
- `prompts/heartbeat.md`
- `prompts/morning_brief.md`
- `prompts/weekly_review.md`
- `skills/*/SKILL.md`：可載入 skills

## Prompt 與排程客製

排程 prompt 檔支援 YAML frontmatter：

- `tools`: 允許工具清單
- `max_turns`: 最大回合數
- `suppress_token`: 若模型輸出此 token，則不發送訊息（常用於 heartbeat 無事可報）

範例請參考 `workspace/prompts/*.md`。

## 專案結構

```text
app/
  main.py                # FastAPI lifecycle, channels + scheduler startup
  channels/              # Telegram / Slack handlers
  agent/                 # runtime, backend, prompt, skills, tools
  scheduler/             # jobs, prompt loader, delivery, runner
  sessions/              # SQLite session store + manager
  mcp/                   # memory MCP server/tools
tests/                   # pytest 測試
workspace/               # prompts, skills, memory, soul
```

## 安全注意事項

- 請勿提交任何 secrets。
- `.env`、`client_secret*.json`、runtime SQLite/memory artifacts 已在忽略清單中。
