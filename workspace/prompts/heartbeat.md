---
schedule: "*/30 * * * *"
tools:
  - WebSearch
  - mcp__memory__memory_search
max_turns: 8
suppress_token: HEARTBEAT_OK
---
Review recent memory and anything time-sensitive that deserves attention within the next 2 hours.

Only alert me for items that are:
- overdue, or
- due today, or
- time-critical within the next 2 hours.

If there is nothing clearly urgent, respond with ONLY the single token: HEARTBEAT_OK

Do NOT include process narration.
Do NOT write to memory.
