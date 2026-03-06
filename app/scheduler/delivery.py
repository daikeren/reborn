from __future__ import annotations

import functools
import logging

from telegram import Bot

from app.utils import send_html, split_message

logger = logging.getLogger(__name__)


async def deliver_to_telegram(bot: Bot, chat_id: int, text: str) -> None:
    """Send text to a Telegram chat, splitting long messages.

    Uses HTML parse_mode with automatic fallback to plain text.
    Exceptions are caught and logged so one failed chunk doesn't crash the caller.
    """
    if not text or not text.strip():
        return

    for chunk in split_message(text):
        try:
            await send_html(
                functools.partial(bot.send_message, chat_id=chat_id),
                chunk,
            )
        except Exception:
            logger.exception("Failed to send Telegram message to %s", chat_id)
