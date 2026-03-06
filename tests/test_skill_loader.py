from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agent.skills import (
    filter_available_skill_rows,
    is_skill_available,
    load_all_skills,
    load_skill,
)


@pytest.fixture()
def skills_dir(workspace: Path) -> Path:
    d = workspace / "skills"
    d.mkdir()
    return d


def _write_skill(skills_dir: Path, name: str, content: str) -> Path:
    """Create workspace/skills/{name}/SKILL.md with the given content."""
    d = skills_dir / name
    d.mkdir(exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# load_skill — single file
# ---------------------------------------------------------------------------


def test_full_frontmatter(skills_dir: Path):
    _write_skill(
        skills_dir,
        "researcher",
        """\
---
description: Use this skill for web research tasks
tools:
  - WebSearch
  - WebFetch
model: haiku
---
You are a web researcher. Search the web and summarize findings.
""",
    )
    name, defn = load_skill(skills_dir / "researcher" / "SKILL.md")
    assert name == "researcher"
    assert defn.description == "Use this skill for web research tasks"
    assert defn.tools == ["WebSearch", "WebFetch"]
    assert defn.model == "haiku"
    assert "web researcher" in defn.prompt


def test_tools_omitted_inherits_none(skills_dir: Path):
    _write_skill(
        skills_dir,
        "helper",
        """\
---
description: A general helper skill
---
You help with everything.
""",
    )
    _, defn = load_skill(skills_dir / "helper" / "SKILL.md")
    assert defn.tools is None


def test_model_omitted_defaults_none(skills_dir: Path):
    _write_skill(
        skills_dir,
        "helper",
        """\
---
description: A helper
---
Help out.
""",
    )
    _, defn = load_skill(skills_dir / "helper" / "SKILL.md")
    assert defn.model is None


def test_description_required(skills_dir: Path):
    _write_skill(
        skills_dir,
        "bad",
        """\
---
tools:
  - WebSearch
---
No description here.
""",
    )
    with pytest.raises(ValueError, match="description"):
        load_skill(skills_dir / "bad" / "SKILL.md")


def test_empty_prompt_body_raises(skills_dir: Path):
    _write_skill(
        skills_dir,
        "empty",
        """\
---
description: Has a description
---
""",
    )
    with pytest.raises(ValueError, match="prompt"):
        load_skill(skills_dir / "empty" / "SKILL.md")


def test_whitespace_only_body_raises(skills_dir: Path):
    _write_skill(
        skills_dir,
        "ws",
        """\
---
description: Has a description
---
   \n  \n
""",
    )
    with pytest.raises(ValueError, match="prompt"):
        load_skill(skills_dir / "ws" / "SKILL.md")


def test_name_from_directory(skills_dir: Path):
    _write_skill(
        skills_dir,
        "my-cool-skill",
        """\
---
description: Cool skill
---
Do cool things.
""",
    )
    name, _ = load_skill(skills_dir / "my-cool-skill" / "SKILL.md")
    assert name == "my-cool-skill"


# ---------------------------------------------------------------------------
# load_all_skills
# ---------------------------------------------------------------------------


def test_load_all_skills_returns_dict(skills_dir: Path):
    _write_skill(
        skills_dir,
        "alpha",
        """\
---
description: Alpha skill
---
Alpha prompt.
""",
    )
    _write_skill(
        skills_dir,
        "beta",
        """\
---
description: Beta skill
---
Beta prompt.
""",
    )
    result = load_all_skills()
    assert isinstance(result, dict)
    assert set(result.keys()) == {"alpha", "beta"}


def test_empty_skills_dir(skills_dir: Path):
    result = load_all_skills()
    assert result == {}


def test_nonexistent_skills_dir(workspace: Path):
    # skills/ directory doesn't exist at all
    result = load_all_skills()
    assert result == {}


def test_dirs_without_skill_md_skipped(skills_dir: Path):
    _write_skill(
        skills_dir,
        "valid",
        """\
---
description: Valid
---
Valid prompt.
""",
    )
    # A directory without SKILL.md
    (skills_dir / "incomplete").mkdir()
    (skills_dir / "incomplete" / "README.md").write_text("not a skill")
    # A plain file at the top level
    (skills_dir / "stray.txt").write_text("not a skill")
    result = load_all_skills()
    assert list(result.keys()) == ["valid"]


def test_malformed_yaml_skipped_with_warning(skills_dir: Path, caplog):
    _write_skill(
        skills_dir,
        "good",
        """\
---
description: Good skill
---
Good prompt.
""",
    )
    _write_skill(
        skills_dir,
        "bad",
        """\
---
description: [invalid yaml
  - not: closed
---
Bad prompt.
""",
    )
    result = load_all_skills()
    assert "good" in result
    assert "bad" not in result
    assert any("bad" in r.message for r in caplog.records)


def test_missing_description_skipped_with_warning(skills_dir: Path, caplog):
    _write_skill(
        skills_dir,
        "no-desc",
        """\
---
tools:
  - WebSearch
---
No description.
""",
    )
    result = load_all_skills()
    assert "no-desc" not in result
    assert len(caplog.records) > 0


def test_symlink_dirs_skipped(skills_dir: Path):
    _write_skill(
        skills_dir,
        "real",
        """\
---
description: Real skill
---
Real prompt.
""",
    )
    link = skills_dir / "linked"
    os.symlink(skills_dir / "real", link)
    result = load_all_skills()
    assert "real" in result
    assert "linked" not in result


def test_result_sorted_by_name(skills_dir: Path):
    for name in ["charlie", "alpha", "bravo"]:
        _write_skill(
            skills_dir,
            name,
            f"""\
---
description: {name} skill
---
{name} prompt.
""",
        )
    result = load_all_skills()
    assert list(result.keys()) == ["alpha", "bravo", "charlie"]


def test_load_all_skills_available_only_filters_gated_skills(
    skills_dir: Path, monkeypatch
):
    _write_skill(
        skills_dir,
        "google-workspace",
        """\
---
description: Google Workspace
---
Use gog.
""",
    )
    _write_skill(
        skills_dir,
        "web-researcher",
        """\
---
description: Research
---
Use the web.
""",
    )
    monkeypatch.setattr("app.agent.skills.shutil.which", lambda name: None)
    result = load_all_skills(
        available_only=True,
    )

    assert "web-researcher" in result
    assert "google-workspace" not in result


def test_is_skill_available_for_google_workspace():
    assert is_skill_available("google-workspace", gog_available=True) is True
    assert is_skill_available("google-workspace", gog_available=False) is False


def test_filter_available_skill_rows():
    rows = [
        {"name": "google-workspace"},
        {"name": "web-researcher"},
    ]

    filtered = filter_available_skill_rows(
        rows,
        gog_available=False,
    )

    assert [row["name"] for row in filtered] == ["web-researcher"]
