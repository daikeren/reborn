from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.agent.types import Attachment

SendQuestionCallback = Callable[[list[dict]], Awaitable[None]]


@dataclass(slots=True)
class InteractiveExecutionRequest:
    session_key: str | None
    channel: str | None
    message: str
    chat_key: str | None = None
    attachments: list[Attachment] | None = None
    resume_session_id: str | None = None
    send_question: SendQuestionCallback | None = None
    persist_user_message: bool = True
    stored_role: str = "user"
    stored_message: str | None = None
    session_policy: Literal["default", "telegram"] = "default"


@dataclass(slots=True)
class BackgroundExecutionRequest:
    name: str
    channel: str | None
    prompt: str
    model: str | None = None
    allowed_tools: list[str] | None = None
    max_turns: int = 20
