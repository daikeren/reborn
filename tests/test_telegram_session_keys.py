from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram.ext import CommandHandler, MessageHandler


def _get_message_handler(app):
    for h in app.handlers[0]:
        if isinstance(h, MessageHandler):
            return h.callback
    raise RuntimeError("MessageHandler not found")


def _get_new_handler(app):
    for h in app.handlers[0]:
        if isinstance(h, CommandHandler) and "new" in h.commands:
            return h.callback
    raise RuntimeError("/new CommandHandler not found")


@pytest.mark.asyncio
async def test_telegram_message_uses_chat_scoped_chat_key():
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False

    execution_service = AsyncMock()
    execution_service.run_interactive = AsyncMock(return_value=MagicMock(text="reply"))

    update = MagicMock()
    update.update_id = 1001
    update.message.text = "hello"
    update.message.caption = None
    update.message.photo = []
    update.message.document = None
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock()
    update.message.chat_id = 987654
    update.message.message_id = 456

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.set_message_reaction = AsyncMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm, execution_service)
        handler = _get_message_handler(app)
        await handler(update, context)

    sm.has_pending_question.assert_called_once_with("telegram:chat:987654")
    request = execution_service.run_interactive.await_args.args[0]
    assert request.chat_key == "telegram:chat:987654"
    assert request.session_key is None


@pytest.mark.asyncio
async def test_telegram_new_only_resets_current_chat_session():
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.reset_telegram_session = AsyncMock(return_value="Session reset. Starting fresh.")
    execution_service = AsyncMock()

    update = MagicMock()
    update.update_id = 1002
    update.message.chat_id = 777
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm, execution_service)
        handler = _get_new_handler(app)
        await handler(update, context)

    sm.reset_telegram_session.assert_awaited_once_with("telegram:chat:777")
    update.message.reply_text.assert_awaited_once_with("Session reset. Starting fresh.")
