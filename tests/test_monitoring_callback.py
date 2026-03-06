from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.backends.codex_backend import CodexBackend
from app.agent.types import AgentResult
from app.monitoring.tracker import ExecutionTracker
from app.monitoring.types import ExecutionEvent, ExecutionEventKind


# --- Reuse the fake Codex client from test_streaming.py ---


@dataclass
class _Note:
    method: str
    params: dict


class _FakeCodexClient:
    def __init__(self, notes: list[_Note]):
        self.notes = notes
        self.listed_skills: list[dict] = []
        self.start_kwargs: dict | None = None
        self.turn_kwargs: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def list_skills(self, *, cwd: str, force_reload: bool = True):
        return self.listed_skills

    async def start_thread(self, **kwargs):
        self.start_kwargs = kwargs
        return "thread-new"

    async def resume_thread(self, **kwargs):
        return kwargs["thread_id"]

    async def stream_turn(self, **kwargs):
        self.turn_kwargs = kwargs
        for note in self.notes:
            yield note


def _backend_with_client(fake_client: _FakeCodexClient, monkeypatch) -> CodexBackend:
    backend = CodexBackend()
    monkeypatch.setattr(backend, "create_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.agent.backends.codex_backend.build_system_prompt", lambda **kw: "prompt"
    )
    return backend


def _completed() -> _Note:
    return _Note(
        "turn/completed",
        {"threadId": "thread-new", "turn": {"id": "turn-1", "status": "completed"}},
    )


# --- Backend event emission tests ---


@pytest.mark.asyncio
async def test_codex_emits_tool_use_event(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "toolUse", "name": "WebSearch", "input": "query"}},
        ),
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "result"}}),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    events: list[ExecutionEvent] = []

    async def capture(event: ExecutionEvent) -> None:
        events.append(event)

    await backend.agent_turn("test", on_event=capture)
    kinds = [e.kind for e in events]
    assert ExecutionEventKind.TOOL_USE in kinds
    tool_event = next(e for e in events if e.kind == ExecutionEventKind.TOOL_USE)
    assert tool_event.data["tool"] == "WebSearch"


@pytest.mark.asyncio
async def test_codex_emits_commentary_event(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {
                "item": {
                    "type": "agentMessage",
                    "channel": "commentary",
                    "text": "thinking...",
                }
            },
        ),
        _Note(
            "item/completed",
            {"item": {"type": "agentMessage", "channel": "final", "text": "answer"}},
        ),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    events: list[ExecutionEvent] = []

    async def capture(event: ExecutionEvent) -> None:
        events.append(event)

    await backend.agent_turn("test", on_event=capture)
    kinds = [e.kind for e in events]
    assert ExecutionEventKind.COMMENTARY in kinds
    assert ExecutionEventKind.TEXT_CHUNK in kinds
    assert ExecutionEventKind.TURN_COMPLETED in kinds


@pytest.mark.asyncio
async def test_codex_emits_turn_completed(monkeypatch):
    notes = [
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "done"}}),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    events: list[ExecutionEvent] = []

    async def capture(event: ExecutionEvent) -> None:
        events.append(event)

    await backend.agent_turn("test", on_event=capture)
    assert events[-1].kind == ExecutionEventKind.TURN_COMPLETED


@pytest.mark.asyncio
async def test_codex_emits_tool_result_event(monkeypatch):
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "toolResult", "output": "search results here"}},
        ),
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "done"}}),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    events: list[ExecutionEvent] = []

    async def capture(event: ExecutionEvent) -> None:
        events.append(event)

    await backend.agent_turn("test", on_event=capture)
    kinds = [e.kind for e in events]
    assert ExecutionEventKind.TOOL_RESULT in kinds


@pytest.mark.asyncio
async def test_on_event_none_does_not_raise(monkeypatch):
    """Backward compat: on_event=None (default) works fine."""
    notes = [
        _Note(
            "item/completed",
            {"item": {"type": "toolUse", "name": "WebSearch", "input": "q"}},
        ),
        _Note("item/completed", {"item": {"type": "agentMessage", "text": "result"}}),
        _completed(),
    ]
    backend = _backend_with_client(_FakeCodexClient(notes), monkeypatch)

    # Default on_event=None should not raise
    result = await backend.agent_turn("test")
    assert result.text == "result"


# --- ExecutionService tracker integration test ---


@pytest.mark.asyncio
async def test_execution_service_wires_tracker(workspace: Path):
    """ExecutionService.run_interactive wires ExecutionTracker lifecycle correctly."""
    from app.orchestrator import ExecutionService, InteractiveExecutionRequest
    from app.sessions.manager import SessionManager
    from app.sessions.store import SessionStore

    store = SessionStore(workspace / "test.db")
    manager = SessionManager(store)
    service = ExecutionService(store, manager)

    tracker = ExecutionTracker()

    fake_result = AgentResult(text="hello world", session_id="sid-123")

    with (
        patch("app.orchestrator.service.get_tracker", return_value=tracker),
        patch(
            "app.orchestrator.service.agent_turn",
            new_callable=AsyncMock,
            return_value=fake_result,
        ),
    ):
        result = await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="test:session",
                channel="telegram",
                message="hi",
            )
        )

    assert result is not None
    assert result.text == "hello world"

    # After completion, should be in completed, not active
    assert tracker.list_active() == []
    completed = tracker.list_completed()
    assert len(completed) == 1
    assert completed[0].session_key == "test:session"
    assert completed[0].status == "completed"
    assert completed[0].channel == "telegram"
    assert completed[0].elapsed_ms is not None

    store.close()


@pytest.mark.asyncio
async def test_execution_service_tracker_on_failure(workspace: Path):
    """ExecutionService.run_interactive marks execution as failed on error."""
    from app.orchestrator import ExecutionService, InteractiveExecutionRequest
    from app.sessions.manager import SessionManager
    from app.sessions.store import SessionStore

    store = SessionStore(workspace / "test.db")
    manager = SessionManager(store)
    service = ExecutionService(store, manager)

    tracker = ExecutionTracker()

    with (
        patch("app.orchestrator.service.get_tracker", return_value=tracker),
        patch(
            "app.orchestrator.service.agent_turn",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = await service.run_interactive(
            InteractiveExecutionRequest(
                session_key="test:fail",
                channel="slack",
                message="hi",
            )
        )

    assert result is None

    assert tracker.list_active() == []
    completed = tracker.list_completed()
    assert len(completed) == 1
    assert completed[0].session_key == "test:fail"
    assert completed[0].status == "failed"
    assert completed[0].error_message == "Agent turn failed"

    store.close()
