---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Source+Code+Pro:wght@400;500&display=swap');

  :root {
    --color-bg: #faf6f1;
    --color-surface: #f0ebe4;
    --color-accent: #d97757;
    --color-accent-dark: #b85c3a;
    --color-text: #3d3929;
    --color-heading: #1a1714;
    --color-muted: #8a8070;
    --color-border: #e0d8ce;
  }

  section {
    background: var(--color-bg);
    color: var(--color-text);
    font-family: 'Noto Sans TC', 'Helvetica Neue', sans-serif;
    padding: 50px 70px;
    line-height: 1.7;
  }

  h1 {
    color: var(--color-heading);
    font-size: 2.8em;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  h2 {
    color: var(--color-heading);
    font-size: 1.9em;
    font-weight: 700;
    border-bottom: 2px solid var(--color-accent);
    padding-bottom: 8px;
    margin-bottom: 24px;
  }

  h3 {
    color: var(--color-accent-dark);
    font-size: 1.3em;
    font-weight: 500;
    margin-top: 16px;
  }

  strong {
    color: var(--color-accent-dark);
    font-weight: 700;
  }

  code {
    font-family: 'Source Code Pro', monospace;
    background: rgba(217, 119, 87, 0.1);
    color: var(--color-accent-dark);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.85em;
  }

  pre {
    background: #1a1714 !important;
    border: none;
    border-radius: 12px;
    padding: 24px !important;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  }

  pre code {
    background: transparent !important;
    color: #e8e0d4 !important;
    padding: 0;
    font-size: 0.75em;
    line-height: 1.5;
  }

  ul, ol {
    margin-left: 0;
  }

  li {
    margin-bottom: 6px;
    color: var(--color-text);
  }

  li::marker {
    color: var(--color-accent);
  }

  table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 12px;
    overflow: hidden;
    font-size: 0.9em;
    border: 1px solid var(--color-border);
  }

  th {
    background: var(--color-heading) !important;
    color: var(--color-bg) !important;
    padding: 12px 18px;
    text-align: left;
    font-weight: 700;
  }

  td {
    background: #fff;
    padding: 10px 18px;
    border-bottom: 1px solid var(--color-border);
    color: var(--color-text);
  }

  tr:last-child td {
    border-bottom: none;
  }

  a {
    color: var(--color-accent-dark);
    text-decoration: underline;
    text-decoration-color: rgba(217, 119, 87, 0.4);
    text-underline-offset: 3px;
  }

  section::after {
    color: var(--color-muted);
    font-size: 0.7em;
  }

  blockquote {
    border-left: 3px solid var(--color-accent);
    background: rgba(217, 119, 87, 0.06);
    padding: 14px 22px;
    border-radius: 0 8px 8px 0;
    margin: 16px 0;
  }

  blockquote p {
    color: var(--color-muted);
    font-style: italic;
    margin: 0;
  }

  /* Title slide */
  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: var(--color-bg);
  }

  section.lead h1 {
    font-size: 4.5em;
    margin-bottom: 0;
    color: var(--color-heading);
  }

  section.lead p {
    color: var(--color-muted);
    font-size: 1.2em;
  }

  /* Invert for accent slides */
  section.invert {
    background: var(--color-heading);
    color: var(--color-bg);
  }

  section.invert h1,
  section.invert h2 {
    color: var(--color-bg);
    border-bottom-color: var(--color-accent);
  }

  section.invert code {
    background: rgba(255, 255, 255, 0.1);
    color: var(--color-bg);
  }

  section.invert pre {
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  section.invert pre code {
    color: #e8e0d4 !important;
  }

  section.invert strong {
    color: var(--color-accent);
  }

  /* Two-column layout helper */
  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
    margin-top: 16px;
  }

  .pill {
    display: inline-block;
    background: rgba(217, 119, 87, 0.12);
    color: var(--color-accent-dark);
    border: 1px solid rgba(217, 119, 87, 0.25);
    padding: 4px 14px;
    border-radius: 999px;
    font-size: 0.75em;
    margin-right: 6px;
    margin-bottom: 4px;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Reborn

你的個人 AI 助理服務

整合多通道、Agent Backend、排程、記憶與可擴充 Skills

<span class="pill">Python</span> <span class="pill">FastAPI</span> <span class="pill">Claude SDK</span> <span class="pill">Telegram</span> <span class="pill">Slack</span>

---

## Why Reborn?

<div class="columns">
<div>

- 想要一個**真正屬於自己**的 AI 助理
- 不只是聊天 — 能**主動提醒**、**記住偏好**
- 跨平台：隨時隨地可用
- 可切換 LLM backend

</div>
<div>

> 不是又一個 chatbot wrapper，
> 而是一個有記憶、有主動性、
> 能連接你工具鏈的 AI 夥伴。

</div>
</div>

---

## 架構總覽

```text
                         ┌──────────────┐
                         │   FastAPI    │
                         │   main.py    │
                         └──────┬───────┘
              ┌─────────────────┼─────────────────┐
              v                 v                 v
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
      │   Channels   │  │  Scheduler   │  │  History UI  │
      │  TG / Slack  │  │ APScheduler  │  │  /history    │
      └──────┬───────┘  └──────┬───────┘  └──────────────┘
             │                 │
             v                 v
      ┌────────────────────────────────┐
      │        Agent Runtime           │
      │   Backend Factory  +  Prompt   │
      └──────┬─────────────────┬───────┘
             v                 v
      ┌────────────┐    ┌────────────┐
      │  Sessions  │    │ MCP Tools  │
      │  (SQLite)  │    │ Memory/GWS │
      └────────────┘    └────────────┘
```

---

## 雙通道聊天

<div class="columns">
<div>

### Telegram

- Long polling 模式
- `/new` 指令重置 session
- Typing indicator
- 串流回覆即時更新

</div>
<div>

### Slack

- Socket Mode（無需公開 URL）
- `channel + thread` 維持上下文
- Eyes reaction 表示處理中
- 持續編輯訊息直到完成

</div>
</div>

---

## Agent Runtime

<div class="columns">
<div>

```text
User Message
    │
    v
┌──────────────────┐
│  System Prompt   │
│  + Skills        │
│  + Tools (MCP)   │
└────────┬─────────┘
         v
┌──────────────────┐
│ Backend Factory  │
│ codex / claude   │
└────────┬─────────┘
         v
  Streaming Response
```

</div>
<div>

### System Prompt 組裝

- `SOUL.md` — 身份與行為準則
- `MEMORY.md` — 長期記憶
- 近兩日 memory log
- `workspace/skills/` 動態載入

### Backend 切換

- **Codex** — App Server RPC
- **Claude** — claude-agent-sdk

</div>
</div>

---

## Session 管理

| 特性 | 說明 |
|------|------|
| 儲存引擎 | SQLite — 輕量可靠 |
| Telegram 重置 | 每日 04:00 自動重置 + 閒置 4hr |
| Slack 隔離 | Per-thread session，天然獨立 |
| History UI | `/history` 瀏覽所有對話紀錄 |
| Monitor UI | `/monitor` 查看目前狀態 |

---

## 主動排程

| Job | 頻率 | 用途 |
|-----|------|------|
| `heartbeat` | 每 30 分鐘 | 偵測需主動回報事項 |
| `morning_brief` | 每日 07:00 | 晨間簡報 |
| `weekly_review` | 每週五 18:00 | 週回顧 |

Prompt 檔支援 **YAML frontmatter**：

- `tools` — 允許工具清單
- `max_turns` — 最大回合數
- `suppress_token` — 無事可報時靜默不送出

---

## MCP 能力

<div class="columns">
<div>

### 內建 Memory

- 寫入 / 搜尋 / 更新
- `workspace/MEMORY.md`
- 助理**自主維護**使用者偏好
- 人物、公司、專案資訊

</div>
<div>

### Google Workspace

- 透過 `gogcli` 整合
- 行事曆事件
- Gmail 收件匣
- Google Drive 文件
- Google Tasks 待辦

</div>
</div>

---

## Workspace 結構

```text
workspace/
├── SOUL.md                # 身份與行為準則
├── MEMORY.md              # 事實記憶（助理自主維護）
├── memory/
│   └── 2026-03-06.md      # 每日記錄
├── prompts/
│   ├── heartbeat.md       # 排程 prompt（支援 frontmatter）
│   ├── morning_brief.md
│   └── weekly_review.md
└── skills/
    └── */SKILL.md          # 可擴充 skills
```

---

## 技術棧

<div class="columns">
<div>

| 層級 | 技術 |
|------|------|
| API | FastAPI + Uvicorn |
| Channels | telegram-bot, slack-bolt |
| Agent | claude-agent-sdk |
| Scheduling | APScheduler |

</div>
<div>

| 層級 | 技術 |
|------|------|
| Persistence | SQLite + aiosqlite |
| MCP | FastMCP |
| Logging | Loguru |
| Package Mgr | uv |

</div>
</div>

---

## 快速開始

```bash
# 安裝依賴
uv sync --dev

# 設定環境變數（至少啟用一個通道）
cp .env.example .env

# 啟動服務
uv run uvicorn app.main:app --reload

# 執行測試
uv run pytest
```

> 啟動後可開啟 `http://127.0.0.1:8000/history` 瀏覽對話紀錄

---

## 設計理念

1. **個人優先** — 為單一使用者打造，不追求多租戶
2. **可擴充** — Skills 與 MCP tools 隨插即用
3. **主動性** — 排程系統讓助理不只被動回應
4. **透明** — Session history UI 可回顧所有互動
5. **簡單部署** — SQLite + 單一 FastAPI process

> Keep it simple. Make it personal. Let AI work for you.

---

<!-- _class: invert -->
<!-- _paginate: false -->

# Thank You

**Reborn** — 讓 AI 助理真正為你所用

```
uv run uvicorn app.main:app --reload
```
