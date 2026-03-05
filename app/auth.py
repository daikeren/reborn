from __future__ import annotations

from telegram import Update

from app.config import settings


def verify_telegram(update: Update) -> bool:
    """Null-safe: reject if update has no message or no user."""
    if not update.message or not update.message.from_user:
        return False
    return update.message.from_user.id == settings.allowed_telegram_user_id


def verify_slack(event: dict) -> bool:
    """Reject bot messages, self-messages, and most subtypes (except file_share)."""
    if event.get("bot_id"):
        return False
    subtype = event.get("subtype")
    if subtype and subtype != "file_share":
        return False
    return event.get("user") == settings.allowed_slack_user_id
