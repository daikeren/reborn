from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import settings
from app.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"
ClaudeSkillModel = Literal["sonnet", "opus", "haiku", "inherit"]


@dataclass(frozen=True)
class SkillDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    model: ClaudeSkillModel | None = None


@dataclass(frozen=True)
class SkillStatus:
    name: str
    path: Path
    status: str
    description: str | None = None
    error: str | None = None


def load_skill(path: Path) -> tuple[str, SkillDefinition]:
    """Parse a single SKILL.md file into (name, SkillDefinition).

    The skill name is derived from the parent directory name.
    Raises ValueError if ``description`` is missing or the prompt body is empty.
    """
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)

    name = path.parent.name

    description = meta.get("description")
    if not description:
        raise ValueError(f"{name}: 'description' is required in frontmatter")

    if not body.strip():
        raise ValueError(f"{name}: prompt body must not be empty")

    model = meta.get("model")
    if model is not None and model not in {"sonnet", "opus", "haiku", "inherit"}:
        raise ValueError(f"{name}: 'model' must be one of sonnet, opus, haiku, inherit")

    return name, SkillDefinition(
        description=description,
        prompt=body,
        tools=meta.get("tools"),
        model=model,
    )


def load_all_skills() -> dict[str, SkillDefinition]:
    """Scan ``workspace/skills/*/SKILL.md`` and return a sorted dict of skills.

    Symlink directories are skipped.  Individual file errors are logged as
    warnings without crashing the caller.
    """
    skills_dir = settings.workspace_dir / "skills"
    if not skills_dir.is_dir():
        return {}

    result: dict[str, SkillDefinition] = {}
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        skill_file = entry / SKILL_FILENAME
        if not skill_file.exists():
            continue
        try:
            name, defn = load_skill(skill_file)
            result[name] = defn
        except Exception:
            logger.warning("Skipping invalid skill: %s", entry.name, exc_info=True)

    return result


def inspect_skills() -> list[SkillStatus]:
    skills_dir = settings.workspace_dir / "skills"
    if not skills_dir.is_dir():
        return []

    result: list[SkillStatus] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_symlink():
            result.append(
                SkillStatus(
                    name=entry.name,
                    path=entry,
                    status="blocked",
                    error="Symlink skill directories are skipped",
                )
            )
            continue
        if not entry.is_dir():
            continue
        skill_file = entry / SKILL_FILENAME
        if not skill_file.exists():
            result.append(
                SkillStatus(
                    name=entry.name,
                    path=entry,
                    status="blocked",
                    error="Missing SKILL.md",
                )
            )
            continue
        try:
            name, defn = load_skill(skill_file)
            result.append(
                SkillStatus(
                    name=name,
                    path=skill_file,
                    status="loaded",
                    description=defn.description,
                )
            )
        except Exception as exc:
            logger.warning("Skipping invalid skill: %s", entry.name, exc_info=True)
            result.append(
                SkillStatus(
                    name=entry.name,
                    path=skill_file,
                    status="blocked",
                    error=str(exc),
                )
            )
    return result
