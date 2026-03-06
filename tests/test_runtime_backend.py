from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.backends.factory import get_runtime_backend
from app.agent.runtime import agent_turn
from app.agent.types import AgentError, AgentResult


@pytest.mark.asyncio
async def test_runtime_passes_legacy_unprefixed_session(monkeypatch):
    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(
            return_value=AgentResult(text="ok", session_id="native-new")
        ),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    result = await agent_turn("hello", session_id="legacy-session")

    assert backend.agent_turn.call_args.kwargs["session_id"] == "legacy-session"
    assert result.session_id == "codex:native-new"


@pytest.mark.asyncio
async def test_runtime_passes_native_session_for_matching_prefix(monkeypatch):
    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(
            return_value=AgentResult(text="ok", session_id="thread-2")
        ),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    result = await agent_turn("hello", session_id="codex:thread-1")

    assert backend.agent_turn.call_args.kwargs["session_id"] == "thread-1"
    assert result.session_id == "codex:thread-2"


@pytest.mark.asyncio
async def test_runtime_drops_mismatched_backend_prefix(monkeypatch):
    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(
            return_value=AgentResult(text="ok", session_id="thread-new")
        ),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    result = await agent_turn("hello", session_id="claude:session-1")

    assert backend.agent_turn.call_args.kwargs["session_id"] is None
    assert result.session_id == "codex:thread-new"


@pytest.mark.asyncio
async def test_runtime_keeps_none_session_id(monkeypatch):
    backend = SimpleNamespace(
        name="codex",
        agent_turn=AsyncMock(return_value=AgentResult(text="ok", session_id=None)),
    )
    monkeypatch.setattr("app.agent.runtime.get_runtime_backend", lambda: backend)

    result = await agent_turn("hello")

    assert result.session_id is None


def _set_backend(value: str):
    import app.config

    old = app.config._settings
    app.config._settings = _BackendSettings(agent_backend=value)
    return old


@dataclass(frozen=True)
class _BackendSettings:
    agent_backend: str


def test_backend_factory_selects_codex():
    import app.config

    old = _set_backend("codex")
    try:
        assert get_runtime_backend().name == "codex"
    finally:
        app.config._settings = old


def test_backend_factory_selects_claude():
    import app.config

    old = _set_backend("claude")
    try:
        assert get_runtime_backend().name == "claude"
    finally:
        app.config._settings = old


def test_backend_factory_rejects_invalid_value():
    import app.config

    old = _set_backend("invalid")
    try:
        with pytest.raises(AgentError):
            get_runtime_backend()
    finally:
        app.config._settings = old
