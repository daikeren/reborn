from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.system_prompt import (
    SLACK_FORMATTING,
    TELEGRAM_FORMATTING,
    build_system_prompt,
)


@pytest.fixture(autouse=True)
def _soul_file(workspace: Path):
    (workspace / "SOUL.md").write_text("You are Reborn.")


def test_slack_channel_includes_mrkdwn_guidance(workspace: Path):
    prompt = build_system_prompt(channel="slack")
    assert "*bold*" in prompt
    assert "Do NOT use # headings" in prompt
    assert SLACK_FORMATTING in prompt


def test_telegram_channel_includes_html_guidance(workspace: Path):
    prompt = build_system_prompt(channel="telegram")
    assert "<b>text</b>" in prompt
    assert "Do NOT use Markdown" in prompt
    assert TELEGRAM_FORMATTING in prompt


def test_no_channel_excludes_formatting(workspace: Path):
    prompt = build_system_prompt(channel=None)
    assert SLACK_FORMATTING not in prompt
    assert TELEGRAM_FORMATTING not in prompt


def test_default_channel_is_none(workspace: Path):
    prompt = build_system_prompt()
    assert SLACK_FORMATTING not in prompt
    assert TELEGRAM_FORMATTING not in prompt
