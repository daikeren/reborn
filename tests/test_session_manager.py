from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore


@dataclass
class FakeResult:
    text: str
    session_id: str | None = None


@pytest.fixture()
def manager(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    return SessionManager(store)


# ---------------------------------------------------------------------------
# handle_telegram passes channel="telegram"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_telegram_passes_channel(manager: SessionManager):
    with patch.object(manager, "_run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = FakeResult(text="hi", session_id="s1")
        await manager.handle_telegram(update_id=1, text="hello")

    mock_run.assert_awaited_once()
    assert mock_run.call_args.kwargs["channel"] == "telegram"


# ---------------------------------------------------------------------------
# handle_slack passes channel="slack"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_slack_passes_channel(manager: SessionManager):
    with patch.object(manager, "_run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = FakeResult(text="hi", session_id="s1")
        await manager.handle_slack(
            event_id="e1", channel_id="C1", thread_ts=None, text="hello",
        )

    mock_run.assert_awaited_once()
    assert mock_run.call_args.kwargs["channel"] == "slack"


# ---------------------------------------------------------------------------
# _run_agent passes channel to agent_turn (normal + retry paths)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_passes_channel_to_agent_turn(manager: SessionManager):
    with patch("app.sessions.manager.agent_turn", new_callable=AsyncMock) as mock_at:
        mock_at.return_value = FakeResult(text="ok", session_id="s1")
        await manager._run_agent("key", "msg", channel="telegram")

    mock_at.assert_awaited_once()
    assert mock_at.call_args.kwargs.get("channel") == "telegram"


@pytest.mark.asyncio
async def test_run_agent_retry_passes_channel(manager: SessionManager):
    """When resume fails and retries with session_id=None, channel is preserved."""
    call_count = 0

    async def _fail_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("resume failed")
        return FakeResult(text="ok", session_id="s2")

    with patch("app.sessions.manager.agent_turn", side_effect=_fail_then_succeed):
        result = await manager._run_agent(
            "key", "msg", resume_id="old-sess", channel="telegram",
        )

    assert result is not None
    assert result.text == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_run_agent_persists_message_history(manager: SessionManager):
    with patch("app.sessions.manager.agent_turn", new_callable=AsyncMock) as mock_at:
        mock_at.return_value = FakeResult(text="pong", session_id="s1")
        result = await manager._run_agent("key", "ping", channel="telegram")

    assert result is not None
    messages = manager._store.get_messages("key")
    assert [m.role for m in messages] == ["user", "assistant"]
    assert [m.content for m in messages] == ["ping", "pong"]
