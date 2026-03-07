from __future__ import annotations

import time

from loguru import logger
from telegram import Bot

from app.config import settings
from app.orchestrator import BackgroundExecutionRequest, ExecutionService
from app.scheduler.context_refresh import (
    CONTEXT_REFRESH_JOB,
    build_context_refresh_prompt,
)
from app.scheduler.delivery import deliver_to_telegram
from app.scheduler.prompts import load_job_prompt
from app.utils import now_tz


async def _run_job(
    name: str,
    bot: Bot,
    chat_id: int,
    execution_service: ExecutionService,
) -> None:
    """Generic job runner: load a job definition, call the agent, deliver or suppress."""
    jp = load_job_prompt(name)
    now = now_tz()
    started_at = time.monotonic()
    prompt_body = jp.prompt
    if name == CONTEXT_REFRESH_JOB:
        prompt_body = build_context_refresh_prompt(
            jp.prompt,
            execution_service.session_store,
            now=now,
        )
    prompt = f"Current time: {now.strftime('%Y-%m-%d %H:%M %Z')}\n\n{prompt_body}"
    logger.info(
        "Scheduler job started: name={}, model={}, max_turns={}, tools={}",
        name,
        settings.background_model,
        jp.max_turns,
        ",".join(jp.tools) if jp.tools else "-",
    )

    try:
        result = await execution_service.run_background(
            BackgroundExecutionRequest(
                name=name,
                channel="telegram",
                prompt=prompt,
                model=settings.background_model,
                allowed_tools=jp.tools,
                max_turns=jp.max_turns,
            )
        )
    except Exception:
        logger.exception("Scheduler job failed during agent turn: name={}", name)
        return

    if jp.should_suppress(result.text):
        logger.info(
            "Scheduler job suppressed by policy: name={}, reply_len={}",
            name,
            len(result.text),
        )
        return

    await deliver_to_telegram(bot, chat_id, result.text)
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "Scheduler job delivered: name={}, chat_id={}, reply_len={}, elapsed_ms={}",
        name,
        chat_id,
        len(result.text),
        elapsed_ms,
    )
