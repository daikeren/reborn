from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram.error import BadRequest

from app.config import settings


def now_tz() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def today_tz() -> date:
    return now_tz().date()


def split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split text into chunks of at most max_len characters."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


# ---------------------------------------------------------------------------
# Telegram HTML safe-send helpers
# ---------------------------------------------------------------------------

_PARSE_ERROR_PHRASES = (
    "can't parse entities",
    "unsupported start tag",
    "unsupported end tag",
    "can't find end tag",
    "wrong entity",
)


def _is_parse_error(exc: BadRequest) -> bool:
    """Check if a BadRequest is caused by HTML parse failure."""
    msg = str(exc).lower()
    return any(phrase in msg for phrase in _PARSE_ERROR_PHRASES)


async def send_html(
    send_fn: Callable[..., Awaitable[Any]], text: str, **kwargs: Any
) -> Any:
    """Send with HTML parse_mode, fallback to plain text on parse error."""
    try:
        return await send_fn(text=text, parse_mode="HTML", **kwargs)
    except BadRequest as exc:
        if _is_parse_error(exc):
            return await send_fn(text=text, **kwargs)
        raise
