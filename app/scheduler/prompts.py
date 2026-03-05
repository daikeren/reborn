from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings
from app.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class JobPrompt:
    prompt: str
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    suppress_token: str | None = None

    def should_suppress(self, text: str) -> bool:
        if self.suppress_token is None:
            return False
        stripped = text.strip()
        # Exact match or last line is the suppress token (LLM sometimes adds reasoning)
        return stripped == self.suppress_token or stripped.endswith(self.suppress_token)


def load_job_prompt(name: str) -> JobPrompt:
    """Load a job prompt from workspace/prompts/{name}.md.

    Supports YAML frontmatter for tools, max_turns, and suppress_token.
    """
    path = settings.workspace_dir / "prompts" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    raw = path.read_text()
    meta, body = parse_frontmatter(raw)

    return JobPrompt(
        prompt=body,
        tools=meta.get("tools", []),
        max_turns=meta.get("max_turns", 10),
        suppress_token=meta.get("suppress_token"),
    )
