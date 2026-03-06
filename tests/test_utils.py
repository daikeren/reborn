from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.utils import _is_parse_error, send_html


# ---------------------------------------------------------------------------
# _is_parse_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Can't parse entities",
        "Unsupported start tag at byte offset 5",
        "Unsupported end tag at byte offset 10",
        "Can't find end tag for <b>",
        "Wrong entity: unmatched end tag",
    ],
)
def test_is_parse_error_matches(message: str):
    exc = BadRequest(message)
    assert _is_parse_error(exc) is True


@pytest.mark.parametrize(
    "message",
    [
        "Chat not found",
        "Message is too long",
        "Bot was kicked from the group",
    ],
)
def test_is_parse_error_rejects_non_parse(message: str):
    exc = BadRequest(message)
    assert _is_parse_error(exc) is False


# ---------------------------------------------------------------------------
# send_html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_html_success():
    send_fn = AsyncMock(return_value="ok")
    result = await send_html(send_fn, "Hello <b>world</b>", chat_id=123)
    send_fn.assert_awaited_once_with(
        text="Hello <b>world</b>", parse_mode="HTML", chat_id=123
    )
    assert result == "ok"


@pytest.mark.asyncio
async def test_send_html_parse_error_fallback():
    send_fn = AsyncMock(side_effect=[BadRequest("Can't parse entities"), "fallback_ok"])
    result = await send_html(send_fn, "<bad>text", chat_id=123)
    assert send_fn.await_count == 2
    # Second call: no parse_mode
    second_call = send_fn.await_args_list[1]
    assert "parse_mode" not in second_call.kwargs
    assert second_call.kwargs["text"] == "<bad>text"
    assert result == "fallback_ok"


@pytest.mark.asyncio
async def test_send_html_non_parse_error_raises():
    send_fn = AsyncMock(side_effect=BadRequest("Chat not found"))
    with pytest.raises(BadRequest, match="Chat not found"):
        await send_html(send_fn, "text", chat_id=123)
