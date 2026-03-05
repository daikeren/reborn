from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.skills import load_skill


@pytest.fixture()
def skill_file(workspace: Path) -> Path:
    """Copy the real google-workspace SKILL.md into the test workspace."""
    src = Path(__file__).resolve().parent.parent / "workspace" / "skills" / "google-workspace" / "SKILL.md"
    dest_dir = workspace / "skills" / "google-workspace"
    dest_dir.mkdir(parents=True)
    dest = dest_dir / "SKILL.md"
    dest.write_text(src.read_text())
    return dest


def test_skill_loads_with_correct_name(skill_file: Path):
    name, _ = load_skill(skill_file)
    assert name == "google-workspace"


def test_skill_has_description(skill_file: Path):
    _, defn = load_skill(skill_file)
    assert "Google Workspace" in defn.description


def test_skill_has_bash_tool(skill_file: Path):
    _, defn = load_skill(skill_file)
    assert defn.tools == ["Bash"]


def test_skill_prompt_mentions_gog(skill_file: Path):
    _, defn = load_skill(skill_file)
    assert "gog" in defn.prompt
