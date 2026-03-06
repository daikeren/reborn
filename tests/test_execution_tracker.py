from __future__ import annotations

import time

from app.monitoring.tracker import ExecutionTracker
from app.monitoring.types import (
    ExecutionEvent,
    ExecutionEventKind,
    ExecutionStatus,
    make_event,
)


def test_start_and_list_active():
    tracker = ExecutionTracker()
    ex = tracker.start_execution("sess:1", channel="telegram", backend="claude")
    assert ex.session_key == "sess:1"
    assert ex.channel == "telegram"
    assert ex.backend == "claude"
    assert ex.status == "running"

    active = tracker.list_active()
    assert len(active) == 1
    assert active[0].session_key == "sess:1"


def test_finish_moves_to_completed():
    tracker = ExecutionTracker()
    ex = tracker.start_execution("sess:1")
    ex.mark_completed("reply text", 1234)
    tracker.finish_execution("sess:1")

    assert tracker.list_active() == []
    completed = tracker.list_completed()
    assert len(completed) == 1
    assert completed[0].session_key == "sess:1"
    assert completed[0].status == "completed"
    assert completed[0].elapsed_ms == 1234
    assert completed[0].reply_preview == "reply text"


def test_finish_nonexistent_is_noop():
    tracker = ExecutionTracker()
    tracker.finish_execution("nonexistent")  # should not raise


def test_get_active_and_completed():
    tracker = ExecutionTracker()
    tracker.start_execution("sess:1")
    assert tracker.get_active("sess:1") is not None
    assert tracker.get_active("nonexistent") is None

    tracker.get_active("sess:1").mark_completed("ok", 100)
    tracker.finish_execution("sess:1")
    assert tracker.get_active("sess:1") is None
    assert tracker.get_completed("sess:1") is not None
    assert tracker.get_completed("nonexistent") is None


def test_completed_ring_buffer_eviction():
    tracker = ExecutionTracker()
    for i in range(60):
        key = f"sess:{i}"
        ex = tracker.start_execution(key)
        ex.mark_completed("ok", 100)
        tracker.finish_execution(key)

    completed = tracker.list_completed()
    assert len(completed) == 50
    # Most recent should be first (reversed order)
    assert completed[0].session_key == "sess:59"
    # Oldest kept should be sess:10
    assert completed[-1].session_key == "sess:10"
    # Evicted sessions should not be retrievable
    assert tracker.get_completed("sess:0") is None
    assert tracker.get_completed("sess:9") is None


def test_event_cap():
    ex = ExecutionStatus(session_key="sess:1")
    for i in range(600):
        ex.add_event(ExecutionEvent(kind=ExecutionEventKind.TEXT_CHUNK, data={"i": i}))
    assert len(ex.events) == 500


def test_mark_completed_fields():
    ex = ExecutionStatus(session_key="sess:1")
    ex.mark_completed("This is the reply", 2500)
    assert ex.status == "completed"
    assert ex.elapsed_ms == 2500
    assert ex.reply_preview == "This is the reply"
    assert ex.completed_at is not None
    assert ex.error_message is None


def test_mark_completed_truncates_long_reply():
    ex = ExecutionStatus(session_key="sess:1")
    long_reply = "x" * 1000
    ex.mark_completed(long_reply, 100)
    assert len(ex.reply_preview) == 503  # 500 + "..."
    assert ex.reply_preview.endswith("...")


def test_mark_failed_fields():
    ex = ExecutionStatus(session_key="sess:1")
    ex.mark_failed("something broke", 500)
    assert ex.status == "failed"
    assert ex.elapsed_ms == 500
    assert ex.error_message == "something broke"
    assert ex.completed_at is not None
    assert ex.reply_preview is None


def test_make_event_truncates_text():
    event = make_event(ExecutionEventKind.TEXT_CHUNK, text="a" * 1000)
    assert len(event.data["text"]) == 503  # 500 + "..."

    event = make_event(ExecutionEventKind.TOOL_USE, tool="test", input="b" * 1000)
    assert len(event.data["input"]) == 303  # 300 + "..."
    assert event.data["tool"] == "test"  # short strings not truncated


def test_completed_list_is_most_recent_first():
    tracker = ExecutionTracker()
    for i in range(3):
        key = f"sess:{i}"
        ex = tracker.start_execution(key)
        ex.mark_completed("ok", 100)
        tracker.finish_execution(key)

    completed = tracker.list_completed()
    assert [c.session_key for c in completed] == ["sess:2", "sess:1", "sess:0"]
