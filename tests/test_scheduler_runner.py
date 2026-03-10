from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@dataclass
class FakeChat:
    id: int = 123


def _write_prompt(workspace: Path, name: str, content: str) -> None:
    jobs_dir = workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)
    (jobs_dir / f"{name}.md").write_text(content, encoding="utf-8")


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Reset the module-level singleton between tests."""
    import app.scheduler.runner as runner

    runner._scheduler = None
    yield
    if runner._scheduler is not None:
        if runner._scheduler.running:
            runner._scheduler.shutdown(wait=False)
        runner._scheduler = None


@pytest.fixture(autouse=True)
def _scheduled_prompts(workspace: Path):
    _write_prompt(
        workspace,
        "heartbeat",
        """\
---
schedule: "*/30 * * * *"
---
Heartbeat.
""",
    )
    _write_prompt(
        workspace,
        "morning_brief",
        """\
---
schedule: "0 7 * * *"
---
Morning brief.
""",
    )
    _write_prompt(
        workspace,
        "weekly_review",
        """\
---
schedule: "0 18 * * 5"
---
Weekly review.
""",
    )


@pytest.fixture()
def mock_bot():
    bot = AsyncMock()
    bot.get_chat = AsyncMock(return_value=FakeChat(id=123))
    return bot


@pytest.fixture()
def execution_service():
    service = AsyncMock()
    service.run_background = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_start_registers_scheduled_prompt_jobs(
    workspace: Path, mock_bot, execution_service
):
    from app.scheduler.runner import start_scheduler

    _write_prompt(workspace, "scratchpad", "No schedule here.")

    scheduler = await start_scheduler(mock_bot, execution_service)
    jobs = scheduler.get_jobs()

    assert len(jobs) == 3
    assert {job.id for job in jobs} == {"heartbeat", "morning_brief", "weekly_review"}
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_shutdown_safe_when_not_started(workspace: Path):
    from app.scheduler.runner import shutdown_scheduler

    shutdown_scheduler()


@pytest.mark.asyncio
async def test_scheduler_uses_configured_timezone(
    workspace: Path, mock_bot, execution_service
):
    from app.scheduler.runner import start_scheduler

    scheduler = await start_scheduler(mock_bot, execution_service)

    assert str(scheduler.timezone) == "Asia/Taipei"
    for job in scheduler.get_jobs():
        assert str(job.trigger.timezone) == "Asia/Taipei"
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_double_start_returns_same_scheduler(
    workspace: Path, mock_bot, execution_service
):
    from app.scheduler.runner import start_scheduler

    s1 = await start_scheduler(mock_bot, execution_service)
    s2 = await start_scheduler(mock_bot, execution_service)

    assert s1 is s2
    assert len(s1.get_jobs()) == 3
    s1.shutdown(wait=False)


@pytest.mark.asyncio
async def test_preflight_failure_still_starts(
    workspace: Path, mock_bot, execution_service, caplog
):
    mock_bot.get_chat.side_effect = Exception("Chat not found")

    from app.scheduler.runner import start_scheduler

    with caplog.at_level(logging.WARNING):
        scheduler = await start_scheduler(mock_bot, execution_service)

    assert scheduler is not None
    assert len(scheduler.get_jobs()) == 3
    assert "preflight" in caplog.text.lower() or "chat" in caplog.text.lower()
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_invalid_cron_fails_startup(workspace: Path, mock_bot, execution_service):
    _write_prompt(
        workspace,
        "broken_job",
        """\
---
schedule: "not a cron"
---
Broken.
""",
    )

    from app.scheduler.runner import start_scheduler

    with pytest.raises(ValueError, match="Invalid schedule for prompt 'broken_job'"):
        await start_scheduler(mock_bot, execution_service)


@pytest.mark.asyncio
async def test_runner_registers_generic_job_callable(
    workspace: Path, mock_bot, execution_service
):
    from app.scheduler.runner import start_scheduler

    with patch("app.scheduler.runner._run_job", new=AsyncMock()) as run_job:
        scheduler = await start_scheduler(mock_bot, execution_service)

        await scheduler.get_job("heartbeat").func()

    run_job.assert_awaited_once_with("heartbeat", mock_bot, 0, execution_service)
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_disabled_job_is_not_registered(
    workspace: Path, mock_bot, execution_service
):
    _write_prompt(
        workspace,
        "disabled_job",
        """\
---
schedule: "0 12 * * *"
enabled: false
---
Disabled.
""",
    )

    from app.scheduler.runner import start_scheduler

    scheduler = await start_scheduler(mock_bot, execution_service)
    assert "disabled_job" not in {job.id for job in scheduler.get_jobs()}
    scheduler.shutdown(wait=False)
