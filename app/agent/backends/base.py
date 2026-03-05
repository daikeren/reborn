from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.agent.types import AgentResult, Attachment
from app.monitoring.types import EventCallback

# Callback that receives a list of question dicts from AskUserQuestion
# and returns a dict mapping question text → answer text.
QuestionCallback = Callable[[list[dict]], Awaitable[dict[str, str]]]

DEFAULT_TOOLS: list[str] = [
    "WebSearch",
    "WebFetch",
    "AskUserQuestion",
    "mcp__memory__memory_write",
    "mcp__memory__memory_search",
    "mcp__memory__memory_update_core",
]


class RuntimeBackend(Protocol):
    name: str

    async def agent_turn(
        self,
        message: str,
        *,
        model: str | None = None,
        session_id: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 20,
        mcp_servers: dict | None = None,
        enable_skills: bool = False,
        channel: str | None = None,
        attachments: list[Attachment] | None = None,
        on_event: EventCallback | None = None,
        on_question: QuestionCallback | None = None,
    ) -> AgentResult: ...
