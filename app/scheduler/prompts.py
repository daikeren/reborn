from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import settings
from app.frontmatter import parse_frontmatter

JOB_DEFINITIONS_DIR = "jobs"
LEGACY_PROMPTS_DIR = "prompts"


@dataclass(frozen=True)
class JobPrompt:
    prompt: str
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    suppress_token: str | None = None
    schedule: str | None = None
    enabled: bool = True

    def should_suppress(self, text: str) -> bool:
        if self.suppress_token is None:
            return False
        stripped = text.strip()
        # Exact match or last line is the suppress token (LLM sometimes adds reasoning)
        return stripped == self.suppress_token or stripped.endswith(self.suppress_token)


@dataclass(frozen=True)
class ScheduledJobPrompt:
    name: str
    schedule: str
    path: Path | None = None


def _load_prompt(path: Path) -> JobPrompt:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    if not isinstance(meta, dict):
        raise ValueError(f"Invalid frontmatter in prompt: {path}")

    tools = meta.get("tools", [])
    if tools is None:
        tools = []
    if not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools):
        raise ValueError(f"'tools' must be a list of strings in prompt: {path}")

    max_turns = meta.get("max_turns", 10)
    if isinstance(max_turns, bool) or not isinstance(max_turns, int):
        raise ValueError(f"'max_turns' must be an integer in prompt: {path}")

    suppress_token = meta.get("suppress_token")
    if suppress_token is not None and not isinstance(suppress_token, str):
        raise ValueError(f"'suppress_token' must be a string in prompt: {path}")

    schedule = meta.get("schedule")
    if schedule is not None and not isinstance(schedule, str):
        raise ValueError(f"'schedule' must be a string in prompt: {path}")

    enabled = meta.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"'enabled' must be a boolean in prompt: {path}")

    return JobPrompt(
        prompt=body,
        tools=tools,
        max_turns=max_turns,
        suppress_token=suppress_token,
        schedule=schedule,
        enabled=enabled,
    )


def load_job_prompt(name: str) -> JobPrompt:
    """Load a job definition from workspace/jobs/{name}.md.

    Falls back to the legacy workspace/prompts directory when needed.
    Supports YAML frontmatter for schedule, tools, max_turns, and suppress_token.
    """
    job_path = settings.workspace_dir / JOB_DEFINITIONS_DIR / f"{name}.md"
    legacy_path = settings.workspace_dir / LEGACY_PROMPTS_DIR / f"{name}.md"
    if job_path.exists():
        return _load_prompt(job_path)
    return _load_prompt(legacy_path)


def load_scheduled_job_prompts() -> list[ScheduledJobPrompt]:
    scheduled_by_name: dict[str, ScheduledJobPrompt] = {}
    for dirname in (JOB_DEFINITIONS_DIR, LEGACY_PROMPTS_DIR):
        directory = settings.workspace_dir / dirname
        if not directory.exists():
            continue

        for path in sorted(directory.glob("*.md")):
            if path.stem in scheduled_by_name:
                continue

            prompt = _load_prompt(path)
            if prompt.schedule is None or not prompt.enabled:
                continue

            scheduled_by_name[path.stem] = ScheduledJobPrompt(
                name=path.stem,
                schedule=prompt.schedule,
                path=path,
            )
    return list(scheduled_by_name.values())


def render_job_prompt(job: JobPrompt) -> str:
    meta = {
        "schedule": job.schedule,
        "tools": job.tools,
        "max_turns": job.max_turns,
        "suppress_token": job.suppress_token,
        "enabled": job.enabled,
    }
    cleaned = {key: value for key, value in meta.items() if value is not None}
    frontmatter = yaml.safe_dump(
        cleaned,
        sort_keys=False,
        allow_unicode=False,
    ).strip()
    body = job.prompt.rstrip() + "\n"
    return f"---\n{frontmatter}\n---\n{body}"
