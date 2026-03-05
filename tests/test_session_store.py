from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.sessions.store import SessionStore


@pytest.fixture()
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


# ---------------------------------------------------------------------------
# message_count basics
# ---------------------------------------------------------------------------


def test_new_session_has_zero_message_count(store: SessionStore):
    rec = store.upsert("key1", "sdk1")
    assert rec.message_count == 0


def test_increment_message_count(store: SessionStore):
    store.upsert("key1", "sdk1")
    assert store.increment_message_count("key1") == 1
    assert store.increment_message_count("key1") == 2
    assert store.increment_message_count("key1") == 3


def test_upsert_preserves_count_on_update(store: SessionStore):
    store.upsert("key1", "sdk1")
    store.increment_message_count("key1")
    store.increment_message_count("key1")

    # Upsert again (session resume) — count should be preserved
    rec = store.upsert("key1", "sdk2")
    assert rec.message_count == 2

    # get() also returns preserved count
    fetched = store.get("key1")
    assert fetched is not None
    assert fetched.message_count == 2


def test_delete_and_reupsert_resets_count(store: SessionStore):
    store.upsert("key1", "sdk1")
    store.increment_message_count("key1")
    store.increment_message_count("key1")

    store.delete("key1")
    rec = store.upsert("key1", "sdk_new")
    assert rec.message_count == 0


# ---------------------------------------------------------------------------
# message history
# ---------------------------------------------------------------------------


def test_append_and_get_messages(store: SessionStore):
    store.append_message("key1", "user", "hello", sdk_session_id="sdk1")
    store.append_message("key1", "assistant", "hi there", sdk_session_id="sdk1")

    messages = store.get_messages("key1")
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "hi there"


def test_get_messages_respects_limit(store: SessionStore):
    store.append_message("key1", "user", "one")
    store.append_message("key1", "assistant", "two")
    store.append_message("key1", "user", "three")

    messages = store.get_messages("key1", limit=2)
    assert [m.content for m in messages] == ["two", "three"]


def test_list_sessions_ordered_by_last_active(store: SessionStore):
    store.upsert("a", "sdk-a")
    store.upsert("b", "sdk-b")
    sessions = store.list_sessions(limit=2)
    assert [s.session_key for s in sessions] == ["b", "a"]


def test_list_sessions_pagination_and_count(store: SessionStore):
    store.upsert("a", "sdk-a")
    store.upsert("b", "sdk-b")
    store.upsert("c", "sdk-c")

    assert store.count_sessions() == 3
    page = store.list_sessions(limit=2, offset=1)
    assert [s.session_key for s in page] == ["b", "a"]


def test_list_session_summaries_uses_first_user_message(store: SessionStore):
    store.upsert("a", "sdk-a")
    store.append_message("a", "user", "first question")
    store.append_message("a", "assistant", "first answer")
    store.append_message("a", "user", "second question")

    summaries = store.list_session_summaries(limit=10, offset=0)
    assert len(summaries) == 1
    assert summaries[0].session_key == "a"
    assert summaries[0].first_user_message == "first question"


def test_query_messages_with_since_filter(store: SessionStore):
    store.append_message("key1", "user", "hello")
    cutoff = datetime.now(timezone.utc).isoformat()
    store.append_message("key1", "assistant", "world")

    messages = store.query_messages(session_key="key1", since=cutoff, limit=10)
    assert [m.content for m in messages] == ["world"]


# ---------------------------------------------------------------------------
# get_active_stats
# ---------------------------------------------------------------------------


def test_get_active_stats_aggregate(store: SessionStore):
    store.upsert("a", "sdk_a")
    store.upsert("b", "sdk_b")
    for _ in range(5):
        store.increment_message_count("a")
    for _ in range(3):
        store.increment_message_count("b")

    stats = store.get_active_stats()
    assert stats["active_sessions"] == 2
    assert stats["max_message_count"] == 5
    # No session keys exposed
    assert "session_key" not in str(stats)
    assert "sdk" not in str(stats)


def test_get_active_stats_excludes_stale(store: SessionStore):
    store.upsert("old", "sdk_old")
    store.increment_message_count("old")

    # Manually backdate the last_active to >24h ago
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    store._conn.execute(
        "UPDATE sessions SET last_active = ? WHERE session_key = ?",
        (old_time, "old"),
    )
    store._conn.commit()

    store.upsert("recent", "sdk_recent")
    store.increment_message_count("recent")

    stats = store.get_active_stats()
    assert stats["active_sessions"] == 1
    assert stats["max_message_count"] == 1


def test_get_active_stats_empty(store: SessionStore):
    stats = store.get_active_stats()
    assert stats["active_sessions"] == 0
    assert stats["max_message_count"] == 0


# ---------------------------------------------------------------------------
# Migration: old DB without message_count column / messages table
# ---------------------------------------------------------------------------


def test_migration_adds_message_count_column(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    # Create a legacy DB without the message_count column
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE sessions (
            session_key TEXT PRIMARY KEY,
            sdk_session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_active TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?)",
        ("old_key", "old_sdk", "2025-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    # Opening with SessionStore should migrate
    store = SessionStore(db_path)
    rec = store.get("old_key")
    assert rec is not None
    assert rec.message_count == 0

    # increment works on migrated row
    assert store.increment_message_count("old_key") == 1
    store.append_message("old_key", "user", "legacy prompt")
    messages = store.get_messages("old_key")
    assert len(messages) == 1
    assert messages[0].content == "legacy prompt"
    store.close()
