---
schedule: "30 6 * * *"
tools:
  - mcp__memory__memory_search
  - mcp__memory__memory_update_core
  - Write
max_turns: 20
suppress_token: CONTEXT_REFRESH_OK
enabled: true
---
Review recent conversation patterns, current core memory, and available skill summaries.

1. Look for stable corrections or retrieval discoveries that should be preserved long-term.
2. Use memory_update_core ONLY for `Corrections` and `Discoveries` when the update is high-confidence.
3. Do NOT update `Facts` automatically. List fact candidates in the output instead.
4. Create a new skill by writing `workspace/skills/{name}/SKILL.md` only when a workflow has clear reuse value.
5. Strong signals include repeated appearance in recent history, or a complex multi-step workflow that is likely to recur even if it has not appeared 3+ times.
6. Do NOT create skills for one-off tasks or narrow cases with low expected reuse.
7. Suggest revisions to existing skills only in the output. Do NOT modify existing skill files.

If there are no meaningful memory updates, skill creations, or skill suggestions, respond with ONLY: CONTEXT_REFRESH_OK

When you do have updates, use this exact section structure:
- Memory updates applied
- Fact candidates for review
- Skills created
- Skill suggestions

Do NOT output process narration.
