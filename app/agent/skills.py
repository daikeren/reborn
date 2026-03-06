from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from app.config import settings
from app.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"
ClaudeSkillModel = Literal["sonnet", "opus", "haiku", "inherit"]
OBSIDIAN_SKILLS = frozenset({"obsidian-markdown", "obsidian-bases"})


@dataclass(frozen=True)
class SkillDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    model: ClaudeSkillModel | None = None


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


def has_obsidian_vault(
    extra_writable_roots: Sequence[Path] | None = None,
) -> bool:
    roots = (
        settings.extra_writable_roots
        if extra_writable_roots is None
        else extra_writable_roots
    )
    return any((root / ".obsidian").is_dir() for root in roots)


def is_skill_available(
    name: str,
    *,
    extra_writable_roots: Sequence[Path] | None = None,
    gog_available: bool | None = None,
) -> bool:
    if name == "google-workspace":
        if gog_available is not None:
            return gog_available
        return shutil.which("gog") is not None
    if name in OBSIDIAN_SKILLS:
        return has_obsidian_vault(extra_writable_roots)
    return True


def filter_available_skill_rows(
    skills: list[dict[str, Any]],
    *,
    extra_writable_roots: Sequence[Path] | None = None,
    gog_available: bool | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for skill in skills:
        name = skill.get("name")
        if not isinstance(name, str):
            continue
        if is_skill_available(
            name,
            extra_writable_roots=extra_writable_roots,
            gog_available=gog_available,
        ):
            filtered.append(skill)
    return filtered


def filter_available_skills(
    skills: dict[str, SkillDefinition],
    *,
    extra_writable_roots: Sequence[Path] | None = None,
    gog_available: bool | None = None,
) -> dict[str, SkillDefinition]:
    return {
        name: defn
        for name, defn in skills.items()
        if is_skill_available(
            name,
            extra_writable_roots=extra_writable_roots,
            gog_available=gog_available,
        )
    }


def load_all_skills(*, available_only: bool = False) -> dict[str, SkillDefinition]:
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

    if available_only:
        return filter_available_skills(result)
    return result
