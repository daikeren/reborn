from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@dataclass
class FakeResult:
    text: str
    session_id: str | None = None


@pytest.fixture(autouse=True)
def _prompt_files(workspace: Path):
    """Create prompt files required by all job tests."""
    prompts = workspace / "prompts"
    prompts.mkdir(exist_ok=True)

    (prompts / "heartbeat.md").write_text("""\
---
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 5
suppress_token: HEARTBEAT_OK
---
Check calendar and memory.
""")
    (prompts / "morning_brief.md").write_text("""\
---
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 10
---
Prepare daily brief.
""")
    (prompts / "weekly_review.md").write_text("""\
---
tools:
  - mcp__memory__memory_search
  - Bash
max_turns: 10
---
Prepare weekly review.
""")


# ---------------------------------------------------------------------------
# heartbeat_tick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_suppresses_ok(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_delivers_alert(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Meeting in 15 minutes!")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    bot.send_message.assert_awaited_once()
    assert "Meeting" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_heartbeat_strips_whitespace(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="  HEARTBEAT_OK  \n")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_handles_agent_error(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.side_effect = Exception("SDK crash")
        from app.scheduler.jobs import heartbeat_tick

        # Should not raise
        await heartbeat_tick(bot, 123)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_uses_background_model(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    call_kwargs = mock_agent.call_args.kwargs
    assert call_kwargs["model"] == "gpt-5.3-codex"
    assert call_kwargs["session_id"] is None


@pytest.mark.asyncio
async def test_heartbeat_passes_channel_telegram(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    assert mock_agent.call_args.kwargs["channel"] == "telegram"


@pytest.mark.asyncio
async def test_morning_brief_passes_channel_telegram(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Good morning!")
        from app.scheduler.jobs import morning_brief

        await morning_brief(bot, 123)

    assert mock_agent.call_args.kwargs["channel"] == "telegram"


@pytest.mark.asyncio
async def test_prompt_includes_current_time(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    prompt = mock_agent.call_args.args[0]
    assert prompt.startswith("Current time: ")


@pytest.mark.asyncio
async def test_heartbeat_uses_tools_from_prompt_file(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    call_kwargs = mock_agent.call_args.kwargs
    assert call_kwargs["allowed_tools"] == [
        "mcp__memory__memory_search",
        "Bash",
    ]
    # No memory write tools
    for tool in call_kwargs["allowed_tools"]:
        assert "write" not in tool
        assert "update" not in tool


@pytest.mark.asyncio
async def test_heartbeat_uses_max_turns_from_prompt_file(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="HEARTBEAT_OK")
        from app.scheduler.jobs import heartbeat_tick

        await heartbeat_tick(bot, 123)

    assert mock_agent.call_args.kwargs["max_turns"] == 5


# ---------------------------------------------------------------------------
# morning_brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_morning_brief_delivers(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Good morning! Here's your day...")
        from app.scheduler.jobs import morning_brief

        await morning_brief(bot, 123)

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_morning_brief_isolated_session(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Good morning!")
        from app.scheduler.jobs import morning_brief

        await morning_brief(bot, 123)

    assert mock_agent.call_args.kwargs["session_id"] is None


# ---------------------------------------------------------------------------
# weekly_review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weekly_review_delivers(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Weekly Review: here's your week...")
        from app.scheduler.jobs import weekly_review

        await weekly_review(bot, 123)

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_weekly_review_isolated_session(workspace: Path):
    bot = AsyncMock()
    with patch("app.scheduler.jobs.agent_turn", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = FakeResult(text="Weekly Review!")
        from app.scheduler.jobs import weekly_review

        await weekly_review(bot, 123)

    assert mock_agent.call_args.kwargs["session_id"] is None
