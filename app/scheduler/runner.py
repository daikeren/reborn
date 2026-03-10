from __future__ import annotations

import logging
from functools import partial
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from app.config import settings
from app.orchestrator import ExecutionService
from app.scheduler.jobs import _run_job
from app.scheduler.prompts import load_scheduled_job_prompts

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_scheduler_bot: Bot | None = None
_scheduler_execution_service: ExecutionService | None = None


async def start_scheduler(
    bot: Bot, execution_service: ExecutionService
) -> AsyncIOScheduler:
    """Start the APScheduler with proactive jobs. Singleton — safe to call twice."""
    global _scheduler, _scheduler_bot, _scheduler_execution_service
    if _scheduler is not None:
        return _scheduler

    chat_id = settings.allowed_telegram_user_id
    assert chat_id is not None
    tz = ZoneInfo(settings.timezone)

    # Preflight: validate delivery target
    try:
        await bot.get_chat(chat_id)
        logger.info("Scheduler preflight: chat %s reachable", chat_id)
    except Exception:
        logger.warning(
            "Scheduler preflight: chat %s unreachable, starting anyway", chat_id
        )

    scheduled_jobs = load_scheduled_job_prompts()
    scheduler = AsyncIOScheduler(timezone=tz)

    for job in scheduled_jobs:
        try:
            trigger = CronTrigger.from_crontab(job.schedule, timezone=tz)
        except ValueError as exc:
            raise ValueError(
                f"Invalid schedule for prompt '{job.name}': {job.schedule}"
            ) from exc

        scheduler.add_job(
            partial(_run_job, job.name, bot, chat_id, execution_service),
            trigger=trigger,
            id=job.name,
            replace_existing=True,
        )

    scheduler.start()
    _scheduler = scheduler
    _scheduler_bot = bot
    _scheduler_execution_service = execution_service
    logger.info(
        "Scheduler started with %s jobs: %s",
        len(scheduled_jobs),
        ", ".join(job.name for job in scheduled_jobs) if scheduled_jobs else "-",
    )
    return scheduler


async def reload_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    if _scheduler is None:
        return None
    bot = _scheduler_bot
    execution_service = _scheduler_execution_service
    if bot is None or execution_service is None:
        return None
    shutdown_scheduler()
    return await start_scheduler(bot, execution_service)


async def run_job_now(name: str) -> bool:
    bot = _scheduler_bot
    execution_service = _scheduler_execution_service
    chat_id = settings.allowed_telegram_user_id
    if bot is None or execution_service is None or chat_id is None:
        return False
    await _run_job(name, bot, chat_id, execution_service)
    return True


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler if running."""
    global _scheduler, _scheduler_bot, _scheduler_execution_service
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
        _scheduler = None
    _scheduler_bot = None
    _scheduler_execution_service = None
