---
tools:
  - WebFetch
  - WebSearch
  - mcp__memory__memory_search
  - Bash
max_turns: 10
suppress_token: HEARTBEAT_OK
---
Check my calendar for the next 2 hours (use `gog calendar events --all --today --json`) and review recent memory for anything urgent.

Only report events that have NOT yet started.
Ignore events that are currently ongoing or have already ended — they are not actionable.

Do NOT remind me about tomorrow (or later) reminders/tasks/follow-ups in heartbeat.
Only alert me for items that are:
- overdue, or
- due today, or
- time-critical within the next 2 hours.

If there is something urgent I should know about (upcoming meeting, immediate deadline),
tell me concisely. Keep routine reminders for morning brief.

Output rules (strict):
- Return ONLY final results, never process narration.
- Start directly with actionable content (events/tasks/alerts), or `HEARTBEAT_OK`.
- Keep it compact: no preface, no recap of what tools were used.

If everything looks clear, respond with ONLY the single token: HEARTBEAT_OK
Do NOT include any explanation, reasoning, or other text — just HEARTBEAT_OK by itself.

Do NOT create, update, or delete calendar events — read only.
Do NOT write to memory.
