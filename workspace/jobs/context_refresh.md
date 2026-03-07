---
schedule: "30 6 * * *"
tools:
  - mcp__memory__memory_search
  - mcp__memory__memory_update_core
max_turns: 12
suppress_token: CONTEXT_REFRESH_OK
---
Review recent conversation patterns, current core memory, and available skill summaries.

1. Look for stable corrections or retrieval discoveries that should be preserved long-term.
2. Use memory_update_core ONLY for `Corrections` and `Discoveries` when the update is high-confidence.
3. Do NOT update `Facts` automatically. List fact candidates in the output instead.
4. Suggest new or revised skills only in the output. Do NOT create or edit any files.

If there are no meaningful memory updates or skill suggestions, respond with ONLY: CONTEXT_REFRESH_OK

When you do have updates, use this exact section structure:
- Memory updates applied
- Fact candidates for review
- Skill suggestions

Do NOT output process narration.
