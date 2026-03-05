from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@dataclass
class FakeChat:
    id: int = 123


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the module-level singleton between tests."""
    import app.scheduler.runner as runner

    runner._scheduler = None
    yield
    # Ensure shutdown after test
    if runner._scheduler is not None:
        if runner._scheduler.running:
            runner._scheduler.shutdown(wait=False)
        runner._scheduler = None


@pytest.fixture()
def mock_bot():
    bot = AsyncMock()
    bot.get_chat = AsyncMock(return_value=FakeChat(id=123))
    return bot


@pytest.mark.asyncio
async def test_start_registers_three_jobs(workspace: Path, mock_bot):
    from app.scheduler.runner import start_scheduler

    scheduler = await start_scheduler(mock_bot)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 3
    job_ids = {j.id for j in jobs}
    assert job_ids == {"heartbeat", "morning_brief", "weekly_review"}
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_shutdown_safe_when_not_started(workspace: Path):
    from app.scheduler.runner import shutdown_scheduler

    # Should not raise
    shutdown_scheduler()


@pytest.mark.asyncio
async def test_scheduler_uses_configured_timezone(workspace: Path, mock_bot):
    from app.scheduler.runner import start_scheduler

    scheduler = await start_scheduler(mock_bot)
    assert str(scheduler.timezone) == "Asia/Taipei"
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_double_start_returns_same_scheduler(workspace: Path, mock_bot):
    from app.scheduler.runner import start_scheduler

    s1 = await start_scheduler(mock_bot)
    s2 = await start_scheduler(mock_bot)
    assert s1 is s2
    # Still only 3 jobs
    assert len(s1.get_jobs()) == 3
    s1.shutdown(wait=False)


@pytest.mark.asyncio
async def test_preflight_failure_still_starts(workspace: Path, mock_bot, caplog):
    mock_bot.get_chat.side_effect = Exception("Chat not found")

    from app.scheduler.runner import start_scheduler

    with caplog.at_level(logging.WARNING):
        scheduler = await start_scheduler(mock_bot)

    assert scheduler is not None
    assert len(scheduler.get_jobs()) == 3
    assert "preflight" in caplog.text.lower() or "chat" in caplog.text.lower()
    scheduler.shutdown(wait=False)
