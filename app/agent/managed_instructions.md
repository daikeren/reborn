## Managed Workflow Rules

These instructions are product-managed and apply to all workspaces. Do not ask the user to edit their `SOUL.md` to enable these capabilities.

### Scheduled Jobs

- Jobs are defined in `workspace/jobs/{name}.md` using YAML frontmatter for scheduling.
- When the user asks to create, update, disable, or delete a scheduled job, perform the file change in `workspace/jobs/` directly.
- Always confirm the requested job content and schedule with the user before creating, editing, disabling, or deleting a job.
- After creating, editing, disabling, or deleting a job, run `curl -s -X POST http://localhost:8000/api/scheduler/reload` so the scheduler reloads definitions.
- Job file format:
  ---
  schedule: "0 9 * * 1"
  tools:
    - WebSearch
    - mcp__memory__memory_search
  max_turns: 10
  suppress_token: SUPPRESS_OK
  enabled: true
  ---
  Write the job prompt body below the frontmatter.
- Reload can return `skipped` when the scheduler has not been initialized yet.

### Skills

- Skills are defined in `workspace/skills/{name}/SKILL.md`.
- After writing a new `SKILL.md`, it is available to subsequent interactive agent turns without a reload step.
- When the user asks to create a new skill, or agrees to save a complex reusable workflow as a skill, write the file directly.
- Always confirm with the user before creating or modifying a skill file.
- Skill file format:
  ---
  description: Brief description of what this skill does
  tools:
    - Bash
    - WebSearch
  model: sonnet
  ---
  Write the skill prompt body below the frontmatter.
