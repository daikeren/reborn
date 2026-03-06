from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent.backends.codex_backend import CodexBackend
from app.agent.codex_client import CodexAppServerClient, CodexNotification
from app.agent.types import AgentError


class FakeCodexClient:
    """Minimal fake that satisfies the async context manager protocol."""

    def __init__(self) -> None:
        self.start_thread = AsyncMock(return_value="thread-1")
        self.resume_thread = AsyncMock(return_value="thread-1")
        self.list_skills = AsyncMock(return_value=[])
        self.compact_thread = AsyncMock()
        self._stream_results: list[list[CodexNotification]] = []
        self._stream_call = 0

    async def __aenter__(self) -> FakeCodexClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def stream_turn(self, **kwargs: Any):
        idx = min(self._stream_call, len(self._stream_results) - 1)
        self._stream_call += 1
        for note in self._stream_results[idx]:
            yield note


# -- compact_thread RPC --


@pytest.mark.asyncio
async def test_compact_thread_sends_correct_rpc():
    client = CodexAppServerClient()
    client._request = AsyncMock(return_value=None)

    await client.compact_thread(thread_id="thread-abc")

    client._request.assert_awaited_once_with(
        "thread/compact/start", {"threadId": "thread-abc"}
    )


# -- agent_turn retry on contextWindowExceeded --


@pytest.mark.asyncio
async def test_agent_turn_retries_on_context_window_exceeded(workspace):
    fake = FakeCodexClient()
    fake._stream_results = [
        # First attempt: turn fails with contextWindowExceeded
        [
            CodexNotification(
                method="turn/completed",
                params={
                    "turn": {
                        "id": "t1",
                        "status": "failed",
                        "error": "contextWindowExceeded",
                    }
                },
            ),
        ],
        # Second attempt (after compact): succeeds
        [
            CodexNotification(
                method="item/completed",
                params={"item": {"type": "agentMessage", "text": "Recovered!"}},
            ),
            CodexNotification(
                method="turn/completed",
                params={"turn": {"id": "t2", "status": "completed"}},
            ),
        ],
    ]

    backend = CodexBackend()
    backend.create_client = lambda: fake

    result = await backend.agent_turn("Hello")

    fake.compact_thread.assert_awaited_once_with(thread_id="thread-1")
    assert result.text == "Recovered!"
    assert result.session_id == "thread-1"


@pytest.mark.asyncio
async def test_agent_turn_raises_on_second_context_window_exceeded(workspace):
    fake = FakeCodexClient()
    fake._stream_results = [
        # Both attempts fail with contextWindowExceeded
        [
            CodexNotification(
                method="turn/completed",
                params={
                    "turn": {
                        "id": "t1",
                        "status": "failed",
                        "error": "contextWindowExceeded",
                    }
                },
            ),
        ],
    ]

    backend = CodexBackend()
    backend.create_client = lambda: fake

    with pytest.raises(AgentError, match="Codex turn failed"):
        await backend.agent_turn("Hello")

    fake.compact_thread.assert_awaited_once()


# -- compact notification logging --


@pytest.mark.asyncio
async def test_compact_notifications_logged(workspace, caplog):
    fake = FakeCodexClient()
    fake._stream_results = [
        [
            CodexNotification(
                method="context_compacted",
                params={"threadId": "thread-1"},
            ),
            CodexNotification(
                method="item/completed",
                params={"item": {"type": "contextCompaction"}},
            ),
            CodexNotification(
                method="item/completed",
                params={"item": {"type": "agentMessage", "text": "Done"}},
            ),
            CodexNotification(
                method="turn/completed",
                params={"turn": {"id": "t1", "status": "completed"}},
            ),
        ],
    ]

    backend = CodexBackend()
    backend.create_client = lambda: fake

    with caplog.at_level(logging.INFO):
        result = await backend.agent_turn("Hello")

    assert result.text == "Done"
    assert any(
        "compact notification: context_compacted" in r.message for r in caplog.records
    )
    assert any("context compaction item" in r.message for r in caplog.records)
