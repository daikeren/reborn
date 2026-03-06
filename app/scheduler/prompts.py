from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class JobPrompt:
    prompt: str
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    suppress_token: str | None = None
    schedule: str | None = None

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

    return JobPrompt(
        prompt=body,
        tools=tools,
        max_turns=max_turns,
        suppress_token=suppress_token,
        schedule=schedule,
    )


def load_job_prompt(name: str) -> JobPrompt:
    """Load a job prompt from workspace/prompts/{name}.md.

    Supports YAML frontmatter for schedule, tools, max_turns, and suppress_token.
    """
    path = settings.workspace_dir / "prompts" / f"{name}.md"
    return _load_prompt(path)


def load_scheduled_job_prompts() -> list[ScheduledJobPrompt]:
    prompts_dir = settings.workspace_dir / "prompts"
    if not prompts_dir.exists():
        return []

    scheduled_jobs: list[ScheduledJobPrompt] = []
    for path in sorted(prompts_dir.glob("*.md")):
        prompt = _load_prompt(path)
        if prompt.schedule is None:
            continue
        scheduled_jobs.append(
            ScheduledJobPrompt(
                name=path.stem,
                schedule=prompt.schedule,
                path=path,
            )
        )
    return scheduled_jobs
