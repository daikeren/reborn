from __future__ import annotations

from pathlib import Path

import pytest

from app.scheduler.prompts import (
    ScheduledJobPrompt,
    load_job_prompt,
    load_scheduled_job_prompts,
)


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
schedule: "*/30 * * * *"
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
    assert jp.schedule == "*/30 * * * *"
    assert jp.tools == ["mcp__memory__memory_search", "Bash"]
    assert jp.max_turns == 5
    assert jp.suppress_token == "HEARTBEAT_OK"
    assert jp.prompt.strip() == "Check calendar and memory."


def test_defaults_when_no_frontmatter(prompts_dir: Path):
    _write_prompt(prompts_dir, "simple", "Just do the thing.")
    jp = load_job_prompt("simple")
    assert jp.schedule is None
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
    assert jp.schedule is None
    assert jp.max_turns == 8
    assert jp.tools == []
    assert jp.suppress_token is None
    assert jp.prompt.strip() == "Morning brief here."


def test_load_scheduled_job_prompts_only_returns_scheduled(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "heartbeat",
        """\
---
schedule: "*/30 * * * *"
---
Check calendar and memory.
""",
    )
    _write_prompt(prompts_dir, "notes", "Reusable prompt only.")

    jobs = load_scheduled_job_prompts()

    assert jobs == [
        ScheduledJobPrompt(
            name="heartbeat",
            schedule="*/30 * * * *",
            path=prompts_dir / "heartbeat.md",
        )
    ]


def test_invalid_schedule_type_raises(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "bad_schedule",
        """\
---
schedule:
  - invalid
---
Bad config.
""",
    )

    with pytest.raises(ValueError, match="'schedule' must be a string"):
        load_job_prompt("bad_schedule")


def test_invalid_tools_type_raises(prompts_dir: Path):
    _write_prompt(
        prompts_dir,
        "bad_tools",
        """\
---
tools: Bash
---
Bad config.
""",
    )

    with pytest.raises(ValueError, match="'tools' must be a list of strings"):
        load_job_prompt("bad_tools")


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
