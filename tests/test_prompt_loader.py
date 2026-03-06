from __future__ import annotations

from pathlib import Path

import pytest

from app.scheduler.prompts import JobPrompt, load_job_prompt


@pytest.fixture()
def prompts_dir(workspace: Path) -> Path:
    d = workspace / "prompts"
    d.mkdir()
    return d


def _write_prompt(prompts_dir: Path, name: str, content: str) -> Path:
    p = prompts_dir / f"{name}.md"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def test_full_frontmatter(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "heartbeat",
        """\
---
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 5
suppress_token: HEARTBEAT_OK
---
Check calendar and memory.
""",
    )
    jp = load_job_prompt("heartbeat")
    assert jp.tools == ["mcp__memory__memory_search", "Bash"]
    assert jp.max_turns == 5
    assert jp.suppress_token == "HEARTBEAT_OK"
    assert jp.prompt.strip() == "Check calendar and memory."


def test_defaults_when_no_frontmatter(prompts_dir: Path):
    _write_prompt(prompts_dir, "simple", "Just do the thing.")
    jp = load_job_prompt("simple")
    assert jp.tools == []
    assert jp.max_turns == 10
    assert jp.suppress_token is None
    assert jp.prompt == "Just do the thing."


def test_partial_frontmatter(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "brief",
        """\
---
max_turns: 8
---
Morning brief here.
""",
    )
    jp = load_job_prompt("brief")
    assert jp.max_turns == 8
    assert jp.tools == []
    assert jp.suppress_token is None
    assert jp.prompt.strip() == "Morning brief here."


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


def test_missing_file_raises(prompts_dir: Path):
    with pytest.raises(FileNotFoundError):
        load_job_prompt("nonexistent")


# ---------------------------------------------------------------------------
# JobPrompt.should_suppress
# ---------------------------------------------------------------------------


def test_should_suppress_exact_match(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "hb",
        """\
---
suppress_token: HEARTBEAT_OK
---
Check things.
""",
    )
    jp = load_job_prompt("hb")
    assert jp.should_suppress("HEARTBEAT_OK") is True
    assert jp.should_suppress("  HEARTBEAT_OK  \n") is True
    assert jp.should_suppress("Something else") is False


def test_should_suppress_trailing_token(prompts_dir: Path):
    """LLM sometimes adds reasoning before the suppress token."""
    _write_prompt(
        prompts_dir,
        "hb2",
        """\
---
suppress_token: HEARTBEAT_OK
---
Check things.
""",
    )
    jp = load_job_prompt("hb2")
    verbose = "No events found.\n\nHEARTBEAT_OK"
    assert jp.should_suppress(verbose) is True
    assert jp.should_suppress("HEARTBEAT_OK and more") is False


def test_should_suppress_without_token(prompts_dir: Path):
    _write_prompt(prompts_dir, "no_token", "Do stuff.")
    jp = load_job_prompt("no_token")
    assert jp.should_suppress("anything") is False
