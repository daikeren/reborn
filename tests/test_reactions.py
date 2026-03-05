from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram.ext import MessageHandler


def _get_message_handler(app):
    """Extract the MessageHandler callback from a telegram Application."""
    for h in app.handlers[0]:
        if isinstance(h, MessageHandler):
            return h.callback
    raise RuntimeError("MessageHandler not found")


@pytest.mark.asyncio
async def test_telegram_reaction_set_before_agent():
    """Telegram handler sets 👀 reaction before calling agent."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(return_value="reply")

    update = MagicMock()
    update.update_id = 1
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

    update.message.set_reaction.assert_awaited_once()
    call_args = update.message.set_reaction.call_args
    reactions = call_args[0][0]
    assert reactions[0].emoji == "👀"


@pytest.mark.asyncio
async def test_telegram_reaction_removed_after_agent():
    """Telegram handler removes reaction after agent completes."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(return_value="reply")

    update = MagicMock()
    update.update_id = 2
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

    context.bot.set_message_reaction.assert_awaited_once_with(
        chat_id=123, message_id=456, reaction=[],
    )


@pytest.mark.asyncio
async def test_telegram_reaction_add_failure_doesnt_crash():
    """If set_reaction fails, handler still runs the agent."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(return_value="reply")

    update = MagicMock()
    update.update_id = 3
    update.message.text = "hello"
    update.message.caption = None
    update.message.photo = []
    update.message.document = None
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock(side_effect=Exception("API error"))
    update.message.chat_id = 123
    update.message.message_id = 456

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.set_message_reaction = AsyncMock()

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm)
        handler = _get_message_handler(app)
        await handler(update, context)

    sm.handle_telegram.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_reaction_remove_failure_doesnt_crash():
    """If removing reaction fails, handler still completes."""
    from app.channels.telegram import create_telegram_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_telegram = AsyncMock(return_value="reply")

    update = MagicMock()
    update.update_id = 4
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
    context.bot.set_message_reaction = AsyncMock(side_effect=Exception("API error"))

    with patch("app.channels.telegram.verify_telegram", return_value=True):
        app = create_telegram_app("fake-token", sm)
        handler = _get_message_handler(app)
        await handler(update, context)

    update.message.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_slack_reaction_added_before_agent():
    """Slack handler adds 👀 reaction before calling agent."""
    from app.channels.slack import create_slack_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_slack = AsyncMock(return_value="reply")

    client = AsyncMock()
    say = AsyncMock()

    event = {
        "text": "hello",
        "client_msg_id": "msg-1",
        "channel": "C123",
        "ts": "1234.5678",
        "user": "U123",
    }

    with patch("app.channels.slack.verify_slack", return_value=True):
        app, _ = create_slack_app("bot-token", "app-token", sm)
        handler_func = app._async_listeners[0].ack_function
        await handler_func(event=event, say=say, client=client)

    client.reactions_add.assert_awaited_once_with(
        name="eyes", channel="C123", timestamp="1234.5678",
    )


@pytest.mark.asyncio
async def test_slack_reaction_removed_after_agent():
    """Slack handler removes reaction after agent completes."""
    from app.channels.slack import create_slack_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_slack = AsyncMock(return_value="reply")

    client = AsyncMock()
    say = AsyncMock()

    event = {
        "text": "hello",
        "client_msg_id": "msg-2",
        "channel": "C123",
        "ts": "1234.5678",
        "user": "U123",
    }

    with patch("app.channels.slack.verify_slack", return_value=True):
        app, _ = create_slack_app("bot-token", "app-token", sm)
        handler_func = app._async_listeners[0].ack_function
        await handler_func(event=event, say=say, client=client)

    client.reactions_remove.assert_awaited_once_with(
        name="eyes", channel="C123", timestamp="1234.5678",
    )


@pytest.mark.asyncio
async def test_slack_reaction_add_failure_doesnt_crash():
    """If reactions_add fails, agent still runs."""
    from app.channels.slack import create_slack_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_slack = AsyncMock(return_value="reply")

    client = AsyncMock()
    client.reactions_add = AsyncMock(side_effect=Exception("API error"))
    say = AsyncMock()

    event = {
        "text": "hello",
        "client_msg_id": "msg-3",
        "channel": "C123",
        "ts": "1234.5678",
        "user": "U123",
    }

    with patch("app.channels.slack.verify_slack", return_value=True):
        app, _ = create_slack_app("bot-token", "app-token", sm)
        handler_func = app._async_listeners[0].ack_function
        await handler_func(event=event, say=say, client=client)

    sm.handle_slack.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_reaction_remove_failure_doesnt_crash():
    """If reactions_remove fails, handler still completes."""
    from app.channels.slack import create_slack_app
    from app.sessions.manager import SessionManager

    sm = AsyncMock(spec=SessionManager)
    sm.has_pending_question.return_value = False
    sm.handle_slack = AsyncMock(return_value="reply")

    client = AsyncMock()
    client.reactions_remove = AsyncMock(side_effect=Exception("API error"))
    say = AsyncMock()

    event = {
        "text": "hello",
        "client_msg_id": "msg-4",
        "channel": "C123",
        "ts": "1234.5678",
        "user": "U123",
    }

    with patch("app.channels.slack.verify_slack", return_value=True):
        app, _ = create_slack_app("bot-token", "app-token", sm)
        handler_func = app._async_listeners[0].ack_function
        await handler_func(event=event, say=say, client=client)

    say.assert_awaited()
