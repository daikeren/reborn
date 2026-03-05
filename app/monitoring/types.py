from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionEventKind(str, Enum):
    TURN_START = "turn_start"
    TEXT_CHUNK = "text_chunk"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    COMMENTARY = "commentary"
    TURN_COMPLETED = "turn_completed"
    ERROR = "error"


@dataclass
class ExecutionEvent:
    kind: ExecutionEventKind
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


_TEXT_PREVIEW_LIMIT = 500
_TOOL_PREVIEW_LIMIT = 300


def make_event(kind: ExecutionEventKind, **data: Any) -> ExecutionEvent:
    """Create an event with truncated previews for large text fields."""
    cleaned: dict[str, Any] = {}
    for key, val in data.items():
        if isinstance(val, str):
            limit = _TOOL_PREVIEW_LIMIT if key in ("input", "output") else _TEXT_PREVIEW_LIMIT
            if len(val) > limit:
                val = val[:limit] + "..."
        cleaned[key] = val
    return ExecutionEvent(kind=kind, data=cleaned)


@dataclass
class ExecutionStatus:
    session_key: str
    channel: str | None = None
    backend: str | None = None
    started_at: float = field(default_factory=time.time)
    status: str = "running"  # running | completed | failed
    current_turn: int = 0
    tools_used: list[str] = field(default_factory=list)
    events: list[ExecutionEvent] = field(default_factory=list)
    completed_at: float | None = None
    elapsed_ms: int | None = None
    reply_preview: str | None = None
    error_message: str | None = None

    _MAX_EVENTS = 500

    def add_event(self, event: ExecutionEvent) -> None:
        if len(self.events) < self._MAX_EVENTS:
            self.events.append(event)

    def mark_completed(self, reply_text: str, elapsed_ms: int) -> None:
        self.status = "completed"
        self.completed_at = time.time()
        self.elapsed_ms = elapsed_ms
        self.reply_preview = reply_text[:500] + "..." if len(reply_text) > 500 else reply_text

    def mark_failed(self, error_message: str, elapsed_ms: int) -> None:
        self.status = "failed"
        self.completed_at = time.time()
        self.elapsed_ms = elapsed_ms
        self.error_message = error_message


EventCallback = Callable[[ExecutionEvent], Awaitable[None]]
