from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.sessions.manager import SessionManager
from app.sessions.store import SessionRecord, SessionStore


@pytest.fixture()
def manager(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    return SessionManager(store)


def _record(*, created_at: datetime, last_active: datetime) -> SessionRecord:
    return SessionRecord(
        session_key="telegram:dm",
        sdk_session_id="sid-1",
        created_at=created_at.isoformat(),
        last_active=last_active.isoformat(),
        message_count=0,
    )


def test_should_resume_telegram_for_fresh_session(manager: SessionManager):
    now = datetime.now(timezone.utc)
    record = _record(
        created_at=now - timedelta(minutes=30),
        last_active=now - timedelta(minutes=10),
    )

    assert manager.should_resume_telegram(record) is True


def test_should_not_resume_telegram_for_idle_session(manager: SessionManager):
    now = datetime.now(timezone.utc)
    record = _record(
        created_at=now - timedelta(hours=1),
        last_active=now - timedelta(hours=5),
    )

    assert manager.should_resume_telegram(record) is False
    assert manager.telegram_reset_reason(record) == "idle_timeout"


@pytest.mark.asyncio
async def test_register_and_resolve_pending_question(manager: SessionManager):
    future = manager.register_pending_question(
        "telegram:dm",
        [{"question": "Pick one", "options": [{"label": "A"}]}],
    )

    assert manager.has_pending_question("telegram:dm") is True
    assert manager.resolve_pending_question("telegram:dm", "A") is True
    assert await future == "A"


@pytest.mark.asyncio
async def test_build_question_handler_parses_selected_option(manager: SessionManager):
    sent: list[list[dict]] = []

    async def send_question(questions: list[dict]) -> None:
        sent.append(questions)
        await asyncio.sleep(0)
        manager.resolve_pending_question("telegram:dm", "1")

    handler = manager.build_question_handler("telegram:dm", send_question)
    assert handler is not None

    result = await handler(
        [
            {
                "question": "Preferred channel?",
                "options": [{"label": "Telegram"}, {"label": "Slack"}],
            }
        ]
    )

    assert sent
    assert result == {"Preferred channel?": "Telegram"}


@pytest.mark.asyncio
async def test_reset_telegram_session_deletes_requested_session_key(
    manager: SessionManager,
):
    manager._store.upsert("telegram:chat:123", "sid-1")
    manager._store.upsert("telegram:chat:456", "sid-2")

    reply = await manager.reset_telegram_session("telegram:chat:123")

    assert reply == "Session reset. Starting fresh."
    assert manager._store.get("telegram:chat:123") is None
    assert manager._store.get("telegram:chat:456") is not None
