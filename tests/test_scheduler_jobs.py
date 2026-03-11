from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.sessions.store import SessionStore


@dataclass
class FakeResult:
    text: str
    session_id: str | None = None


def _write_prompt(workspace: Path, name: str, content: str) -> None:
    jobs = workspace / "jobs"
    jobs.mkdir(exist_ok=True)
    (jobs / f"{name}.md").write_text(content, encoding="utf-8")


@pytest.fixture()
def execution_service(workspace: Path):
    service = AsyncMock()
    service.run_background = AsyncMock()
    service.session_store = SessionStore(workspace / "sessions.db")
    yield service
    service.session_store.close()


@pytest.fixture(autouse=True)
def _job_files(workspace: Path):
    _write_prompt(
        workspace,
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
    _write_prompt(
        workspace,
        "morning_brief",
        """\
---
schedule: "0 7 * * *"
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 10
---
Prepare daily brief.
""",
    )
    _write_prompt(
        workspace,
        "context_refresh",
        """\
---
schedule: "30 6 * * *"
tools:
  - mcp__memory__memory_search
  - mcp__memory__memory_update_core
  - Write
max_turns: 20
suppress_token: CONTEXT_REFRESH_OK
enabled: true
---
Refresh context.
Do NOT update `Facts` automatically.
Create a new skill only when a workflow has clear reuse value.
Strong signals include repeated occurrence or a complex multi-step workflow likely to recur.
Do NOT modify existing skill files.
Use this exact section structure:
- Memory updates applied
- Fact candidates for review
- Skills created
- Skill suggestions
""",
    )
    _write_prompt(
        workspace,
        "weekly_review",
        """\
---
schedule: "0 18 * * 5"
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 10
---
Prepare weekly review.
""",
    )


@pytest.mark.asyncio
async def test_job_suppresses_when_output_matches_token(
    workspace: Path, execution_service
):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_delivers_alert(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="Meeting in 15 minutes!"
    )

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    bot.send_message.assert_awaited_once()
    assert "Meeting" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_job_strips_whitespace_for_suppression(
    workspace: Path, execution_service
):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="  HEARTBEAT_OK  \n"
    )

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_handles_agent_error(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.side_effect = Exception("SDK crash")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_uses_background_model(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.model == "gpt-5.4"


@pytest.mark.asyncio
async def test_job_passes_channel_telegram(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.channel == "telegram"


@pytest.mark.asyncio
async def test_prompt_includes_current_time(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.prompt.startswith("Current time: ")


@pytest.mark.asyncio
async def test_job_uses_tools_from_prompt_file(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.allowed_tools == [
        "mcp__memory__memory_search",
        "Bash",
    ]
    for tool in request.allowed_tools:
        assert "write" not in tool
        assert "update" not in tool


@pytest.mark.asyncio
async def test_job_uses_max_turns_from_prompt_file(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(text="HEARTBEAT_OK")

    from app.scheduler.jobs import _run_job

    await _run_job("heartbeat", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.max_turns == 5


@pytest.mark.asyncio
async def test_morning_brief_prompt_delivers(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="Good morning! Here's your day..."
    )

    from app.scheduler.jobs import _run_job

    await _run_job("morning_brief", bot, 123, execution_service)

    bot.send_message.assert_awaited_once()
    request = execution_service.run_background.call_args.args[0]
    assert request.name == "morning_brief"
    assert request.channel == "telegram"


@pytest.mark.asyncio
async def test_context_refresh_prompt_includes_recent_history_and_skill_summaries(
    workspace: Path, execution_service
):
    skills_dir = workspace / "skills" / "google-workspace"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        """\
---
description: Use this skill for Google Workspace tasks.
---
Use gog.
""",
        encoding="utf-8",
    )
    execution_service.session_store.append_message(
        "telegram:dm",
        "user",
        "Please use terse answers and check calendar before email.",
    )
    execution_service.session_store.append_message(
        "telegram:dm",
        "user",
        "Prepare for my meeting with Sarah using email and notes.",
    )
    execution_service.session_store.append_message(
        "telegram:dm",
        "user",
        "Prepare for my meeting with Sarah using email and notes.",
    )
    execution_service.session_store.append_message(
        "scheduler:heartbeat",
        "assistant",
        "Weekly Review: repeated scheduler output should be ignored.",
    )
    execution_service.run_background.return_value = FakeResult(
        text="CONTEXT_REFRESH_OK"
    )

    from app.scheduler.jobs import _run_job

    await _run_job("context_refresh", AsyncMock(), 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert "## Recent Message History" in request.prompt
    assert "## Available Skill Summaries" in request.prompt
    assert (
        "google-workspace: Use this skill for Google Workspace tasks." in request.prompt
    )
    assert (
        "[telegram:dm] [user] Please use terse answers and check calendar before email."
        in request.prompt
    )
    assert (
        "[telegram:dm] [user] Prepare for my meeting with Sarah using email and notes."
        in request.prompt
    )
    assert "Please use terse answers and check calendar before email." in request.prompt
    assert "scheduler:heartbeat" not in request.prompt
    assert (
        "Create a new skill only when a workflow has clear reuse value."
        in request.prompt
    )
    assert (
        "Strong signals include repeated occurrence or a complex multi-step workflow likely to recur."
        in request.prompt
    )
    assert "Do NOT modify existing skill files." in request.prompt
    assert "- Skills created" in request.prompt
    assert "- Skill suggestions" in request.prompt


@pytest.mark.asyncio
async def test_context_refresh_suppresses_when_output_matches_token(
    workspace: Path, execution_service
):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="CONTEXT_REFRESH_OK"
    )

    from app.scheduler.jobs import _run_job

    await _run_job("context_refresh", bot, 123, execution_service)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_refresh_uses_memory_update_tool_only_for_core_updates(
    workspace: Path, execution_service
):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="CONTEXT_REFRESH_OK"
    )

    from app.scheduler.jobs import _run_job

    await _run_job("context_refresh", bot, 123, execution_service)

    request = execution_service.run_background.call_args.args[0]
    assert request.allowed_tools == [
        "mcp__memory__memory_search",
        "mcp__memory__memory_update_core",
        "Write",
    ]
    assert "Do NOT update `Facts` automatically." in request.prompt
    assert "clear reuse value" in request.prompt
    assert "complex multi-step workflow likely to recur" in request.prompt


@pytest.mark.asyncio
async def test_weekly_review_prompt_delivers(workspace: Path, execution_service):
    bot = AsyncMock()
    execution_service.run_background.return_value = FakeResult(
        text="Weekly Review: here's your week..."
    )

    from app.scheduler.jobs import _run_job

    await _run_job("weekly_review", bot, 123, execution_service)

    bot.send_message.assert_awaited_once()
    request = execution_service.run_background.call_args.args[0]
    assert request.name == "weekly_review"
