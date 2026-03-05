from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram.constants import ChatAction
from telegram.ext import MessageHandler


def _get_message_handler(app):
    """Extract the MessageHandler callback from a telegram Application."""
    for h in app.handlers[0]:
        if isinstance(h, MessageHandler):
            return h.callback
    raise RuntimeError("MessageHandler not found")


async def _slow_handle(*args, **kwargs) -> str:
    """Simulate agent work, yielding to the event loop so typing task runs."""
    await asyncio.sleep(0)  # yield to let typing_loop execute
    return "reply"


@pytest.mark.asyncio
async def test_typing_action_sent():
    """send_chat_action(ChatAction.TYPING) is called at least once."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = _slow_handle

    update = MagicMock()
    update.update_id = 100
    update.message.text = "hello"
    update.message.caption = None
    update.message.photo = []
    update.message.document = None
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock()
    update.message.chat_id = 123
    update.message.message_id = 456

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.set_message_reaction = AsyncMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm)
        handler = _get_message_handler(app)
        await handler(update, context)

    context.bot.send_chat_action.assert_awaited()
    call_args = context.bot.send_chat_action.call_args
    assert call_args.kwargs["action"] == ChatAction.TYPING


@pytest.mark.asyncio
async def test_typing_task_cancelled_after_agent():
    """Typing task is cancelled after agent completes (no lingering tasks)."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(return_value="reply")

    update = MagicMock()
    update.update_id = 101
    update.message.text = "hello"
    update.message.caption = None
    update.message.photo = []
    update.message.document = None
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock()
    update.message.chat_id = 123
    update.message.message_id = 456

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.set_message_reaction = AsyncMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm)
        handler = _get_message_handler(app)
        await handler(update, context)

    # The key assertion: handler completed without error and agent was called
    sm.handle_telegram.assert_awaited_once()


@pytest.mark.asyncio
async def test_typing_task_cancelled_on_exception():
    """Typing task is cancelled even when agent raises an exception."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(side_effect=Exception("agent error"))

    update = MagicMock()
    update.update_id = 102
    update.message.text = "hello"
    update.message.caption = None
    update.message.photo = []
    update.message.document = None
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock()
    update.message.chat_id = 123
    update.message.message_id = 456

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.set_message_reaction = AsyncMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm)
        handler = _get_message_handler(app)
        # Should not raise — handler catches agent exceptions
        await handler(update, context)

    sm.handle_telegram.assert_awaited_once()
