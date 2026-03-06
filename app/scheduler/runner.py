from __future__ import annotations

import logging
from functools import partial
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot

from app.config import settings
from app.orchestrator import ExecutionService
from app.scheduler.jobs import heartbeat_tick, morning_brief, weekly_review

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def start_scheduler(
    bot: Bot, execution_service: ExecutionService
) -> AsyncIOScheduler:
    """Start the APScheduler with proactive jobs. Singleton — safe to call twice."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    chat_id = settings.allowed_telegram_user_id
    tz = ZoneInfo(settings.timezone)

    # Preflight: validate delivery target
    try:
        await bot.get_chat(chat_id)
        logger.info("Scheduler preflight: chat %s reachable", chat_id)
    except Exception:
        logger.warning(
            "Scheduler preflight: chat %s unreachable, starting anyway", chat_id
        )

    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(
        partial(heartbeat_tick, bot, chat_id, execution_service),
        trigger=IntervalTrigger(minutes=30, timezone=tz),
        id="heartbeat",
        replace_existing=True,
    )
    scheduler.add_job(
        partial(morning_brief, bot, chat_id, execution_service),
        trigger=CronTrigger(hour=7, minute=0, timezone=tz),
        id="morning_brief",
        replace_existing=True,
    )
    scheduler.add_job(
        partial(weekly_review, bot, chat_id, execution_service),
        trigger=CronTrigger(day_of_week="fri", hour=18, minute=0, timezone=tz),
        id="weekly_review",
        replace_existing=True,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started with 3 jobs")
    return scheduler


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
        _scheduler = None
