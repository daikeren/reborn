from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import BadRequest

from app.scheduler.delivery import deliver_to_telegram


@pytest.mark.asyncio
async def test_long_message_split():
    bot = AsyncMock()
    text = "A" * 5000  # > 4096 → 2 chunks
    await deliver_to_telegram(bot, 123, text)
    # send_html is used per chunk; 2 chunks expected
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_single_message():
    bot = AsyncMock()
    await deliver_to_telegram(bot, 123, "Hello")
    bot.send_message.assert_awaited_once()
    call = bot.send_message.await_args
    assert call.kwargs["text"] == "Hello"
    assert call.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_empty_text_skipped():
    bot = AsyncMock()
    await deliver_to_telegram(bot, 123, "")
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_whitespace_text_skipped():
    bot = AsyncMock()
    await deliver_to_telegram(bot, 123, "   \n  ")
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_exception_logged_not_raised(caplog):
    bot = AsyncMock()
    bot.send_message.side_effect = Exception("network error")
    with caplog.at_level(logging.ERROR):
        await deliver_to_telegram(bot, 123, "test")
    assert "network error" in caplog.text


@pytest.mark.asyncio
async def test_parse_error_falls_back_to_plain():
    """When HTML parse fails, message is re-sent without parse_mode."""
    bot = AsyncMock()
    bot.send_message.side_effect = [
        BadRequest("Can't parse entities"),
        None,  # fallback succeeds
    ]
    await deliver_to_telegram(bot, 123, "<bad>text")
    assert bot.send_message.await_count == 2
    # Second call has no parse_mode
    second = bot.send_message.await_args_list[1]
    assert "parse_mode" not in second.kwargs


@pytest.mark.asyncio
async def test_non_parse_bad_request_logged(caplog):
    """Non-parse BadRequest is caught by the outer try/except and logged."""
    bot = AsyncMock()
    bot.send_message.side_effect = BadRequest("Chat not found")
    with caplog.at_level(logging.ERROR):
        await deliver_to_telegram(bot, 123, "test")
    assert "Chat not found" in caplog.text
