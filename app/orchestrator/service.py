from __future__ import annotations

import asyncio
import time

from loguru import logger

from app.agent.runtime import AgentResult, agent_turn
from app.config import settings
from app.monitoring.tracker import get_tracker
from app.monitoring.types import ExecutionEvent, ExecutionEventKind
from app.sessions.manager import SessionManager
from app.sessions.store import SessionStore

from .types import BackgroundExecutionRequest, InteractiveExecutionRequest


class ExecutionService:
    """Single entrypoint for interactive and background agent execution."""

    def __init__(self, store: SessionStore, session_manager: SessionManager) -> None:
        self._store = store
        self._session_manager = session_manager
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def run_interactive(
        self,
        request: InteractiveExecutionRequest,
    ) -> AgentResult | None:
        lock_key = request.chat_key or request.session_key
        assert lock_key is not None
        async with self._lock_for(lock_key):
            return await self._run_interactive_locked(request)

    async def run_background(self, request: BackgroundExecutionRequest) -> AgentResult:
        session_key = f"scheduler:{request.name}"
        async with self._lock_for(session_key):
            return await self._run_background_locked(session_key, request)

    def _lock_for(self, session_key: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_key] = lock
        return lock

    @property
    def session_store(self) -> SessionStore:
        return self._store

    async def _run_interactive_locked(
        self,
        request: InteractiveExecutionRequest,
    ) -> AgentResult | None:
        started_at = time.monotonic()
        conversation_key, resume_id, question_scope_key = (
            self._resolve_execution_context(request)
        )
        logger.info(
            "Agent turn started: channel={}, conversation_key={}, chat_key={}, resume={}, attachments={}",
            request.channel or "unknown",
            conversation_key,
            request.chat_key,
            resume_id is not None,
            len(request.attachments) if request.attachments else 0,
        )

        if request.persist_user_message:
            self._store.append_message(
                session_key=conversation_key,
                role="user",
                content=self._stored_user_content(request.message, request.attachments),
                sdk_session_id=resume_id,
            )

        tracker = get_tracker()
        execution = tracker.start_execution(
            conversation_key,
            channel=request.channel,
            backend=settings.agent_backend,
        )

        async def _on_event(event: ExecutionEvent) -> None:
            execution.add_event(event)
            if event.kind == ExecutionEventKind.TOOL_USE:
                tool = event.data.get("tool", "unknown")
                if tool not in execution.tools_used:
                    execution.tools_used.append(tool)
            elif event.kind == ExecutionEventKind.TURN_COMPLETED:
                execution.current_turn += 1

        on_question = self._session_manager.build_question_handler(
            question_scope_key,
            request.send_question,
        )

        try:
            result = await self._call_agent_turn(
                request.message,
                session_id=resume_id,
                channel=request.channel,
                attachments=request.attachments,
                on_event=_on_event,
                on_question=on_question,
            )
        except Exception:
            if resume_id is not None:
                logger.warning(
                    "Resume failed, falling back to new session: conversation_key={}, chat_key={}",
                    conversation_key,
                    request.chat_key,
                )
                try:
                    result = await self._call_agent_turn(
                        request.message,
                        session_id=None,
                        channel=request.channel,
                        attachments=request.attachments,
                        on_event=_on_event,
                        on_question=on_question,
                    )
                except Exception:
                    logger.exception(
                        "Agent turn failed after retry: conversation_key={}",
                        conversation_key,
                    )
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    execution.mark_failed("Agent turn failed after retry", elapsed_ms)
                    tracker.finish_execution(conversation_key)
                    return None
            else:
                logger.exception(
                    "Agent turn failed: conversation_key={}", conversation_key
                )
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                execution.mark_failed("Agent turn failed", elapsed_ms)
                tracker.finish_execution(conversation_key)
                return None

        if result.session_id:
            self._store.upsert(
                conversation_key,
                result.session_id,
                chat_key=request.chat_key,
            )
            count = self._store.increment_message_count(conversation_key)
            if count > 0 and count % 100 == 0:
                logger.warning(
                    "Session message_count milestone: conversation_key={}, count={}",
                    conversation_key,
                    count,
                )

        if result.text:
            self._store.append_message(
                session_key=conversation_key,
                role="assistant",
                content=result.text,
                sdk_session_id=result.session_id or resume_id,
            )

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        execution.mark_completed(result.text, elapsed_ms)
        tracker.finish_execution(conversation_key)
        logger.info(
            "Agent turn completed: channel={}, conversation_key={}, elapsed_ms={}, reply_len={}, has_session_id={}",
            request.channel or "unknown",
            conversation_key,
            elapsed_ms,
            len(result.text),
            result.session_id is not None,
        )
        return result

    async def _run_background_locked(
        self,
        session_key: str,
        request: BackgroundExecutionRequest,
    ) -> AgentResult:
        started_at = time.monotonic()
        logger.info(
            "Background turn started: name={}, channel={}, model={}, max_turns={}",
            request.name,
            request.channel or "unknown",
            request.model,
            request.max_turns,
        )
        tracker = get_tracker()
        execution = tracker.start_execution(
            session_key,
            channel=request.channel,
            backend=settings.agent_backend,
        )

        async def _on_event(event: ExecutionEvent) -> None:
            execution.add_event(event)
            if event.kind == ExecutionEventKind.TOOL_USE:
                tool = event.data.get("tool", "unknown")
                if tool not in execution.tools_used:
                    execution.tools_used.append(tool)
            elif event.kind == ExecutionEventKind.TURN_COMPLETED:
                execution.current_turn += 1

        try:
            result = await agent_turn(
                request.prompt,
                model=request.model,
                session_id=None,
                allowed_tools=request.allowed_tools,
                max_turns=request.max_turns,
                channel=request.channel,
                on_event=_on_event,
            )
        except Exception:
            logger.exception("Background turn failed: name={}", request.name)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            execution.mark_failed("Background turn failed", elapsed_ms)
            tracker.finish_execution(session_key)
            raise

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        execution.mark_completed(result.text, elapsed_ms)
        tracker.finish_execution(session_key)
        logger.info(
            "Background turn completed: name={}, elapsed_ms={}, reply_len={}",
            request.name,
            elapsed_ms,
            len(result.text),
        )
        return result

    async def _call_agent_turn(
        self,
        message: str,
        *,
        session_id: str | None,
        channel: str | None,
        attachments,
        on_event,
        on_question,
    ) -> AgentResult:
        return await agent_turn(
            message,
            session_id=session_id,
            enable_skills=True,
            channel=channel,
            attachments=attachments,
            on_event=on_event,
            on_question=on_question,
        )

    def _resolve_execution_context(
        self,
        request: InteractiveExecutionRequest,
    ) -> tuple[str, str | None, str]:
        if request.session_policy == "telegram":
            chat_key = request.chat_key or request.session_key
            assert chat_key is not None
            if request.session_key is None:
                context = self._session_manager.resolve_telegram_session(chat_key)
                resume_id = request.resume_session_id or context.resume_session_id
                return context.conversation_key, resume_id, chat_key

            if request.resume_session_id is not None:
                return request.session_key, request.resume_session_id, chat_key

            record = self._store.get(request.session_key)
            if record is None:
                return request.session_key, None, chat_key
            if self._session_manager.should_resume_telegram(record):
                return request.session_key, record.sdk_session_id, chat_key
            return request.session_key, None, chat_key

        conversation_key = request.session_key
        assert conversation_key is not None
        if request.resume_session_id is not None:
            return conversation_key, request.resume_session_id, conversation_key

        record = self._store.get(conversation_key)
        return (
            conversation_key,
            record.sdk_session_id if record is not None else None,
            conversation_key,
        )

    @staticmethod
    def _stored_user_content(message: str, attachments) -> str:
        if not attachments:
            return message
        names = ", ".join(att.filename for att in attachments)
        return (
            f"{message}\n[Attachments: {names}]"
            if message
            else f"[Attachments: {names}]"
        )
