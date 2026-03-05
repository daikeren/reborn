from __future__ import annotations

from app.agent.backends.base import DEFAULT_TOOLS, QuestionCallback
from app.agent.backends.factory import get_runtime_backend
from app.agent.session_id import decode_session_id, encode_session_id
from app.agent.types import AgentResult, Attachment
from app.monitoring.types import EventCallback


async def agent_turn(
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
) -> AgentResult:
    backend = get_runtime_backend()
    decoded = decode_session_id(session_id)
    native_session_id: str | None = None
    if decoded:
        if decoded.backend == backend.name:
            native_session_id = decoded.native_id
    elif session_id:
        # Backward compatibility: old stored session IDs had no backend prefix.
        native_session_id = session_id

    result = await backend.agent_turn(
        message,
        model=model,
        session_id=native_session_id,
        allowed_tools=allowed_tools if allowed_tools is not None else DEFAULT_TOOLS,
        max_turns=max_turns,
        mcp_servers=mcp_servers,
        enable_skills=enable_skills,
        channel=channel,
        attachments=attachments,
        on_event=on_event,
        on_question=on_question,
    )
    return AgentResult(
        text=result.text,
        session_id=encode_session_id(backend.name, result.session_id),
    )
