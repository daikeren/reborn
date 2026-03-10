from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from loguru import logger

from app.agent.runtime import AgentResult, agent_turn
from app.config import settings
from app.monitoring.tracker import get_tracker
from app.monitoring.types import ExecutionEvent, ExecutionEventKind, ExecutionStatus
from app.sessions.manager import SessionManager
from app.sessions.store import PENDING_SDK_SESSION_ID, SessionStore

from .types import BackgroundExecutionRequest, InteractiveExecutionRequest


class ExecutionService:
    """Single entrypoint for interactive and background agent execution."""

    def __init__(self, store: SessionStore, session_manager: SessionManager) -> None:
        self._store = store
        self._session_manager = session_manager
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._execution_tasks: dict[str, asyncio.Task[Any]] = {}

    async def run_interactive(
        self,
        request: InteractiveExecutionRequest,
        *,
        execution_id: str | None = None,
    ) -> AgentResult | None:
        prepared = self._prepare_interactive_execution(
            request,
            execution_id=execution_id,
        )
        self._bind_current_task(prepared["execution"].execution_id)
        return await self._run_interactive_prepared(
            request,
            prepared=prepared,
        )

    def start_interactive(self, request: InteractiveExecutionRequest) -> str:
        prepared = self._prepare_interactive_execution(
            request,
            execution_id=uuid4().hex,
        )
        execution_id = prepared["execution"].execution_id
        task = asyncio.create_task(
            self._run_interactive_prepared(
                request,
                prepared=prepared,
            )
        )
        self._register_execution_task(execution_id, task)
        return execution_id

    async def run_background(self, request: BackgroundExecutionRequest) -> AgentResult:
        session_key = f"scheduler:{request.name}"
        execution = get_tracker().start_execution(
            session_key,
            channel=request.channel,
            backend=settings.agent_backend,
        )
        self._bind_current_task(execution.execution_id)
        async with self._lock_for(session_key):
            return await self._run_background_locked(session_key, request, execution)

    def _lock_for(self, session_key: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_key] = lock
        return lock

    @property
    def session_store(self) -> SessionStore:
        return self._store

    def get_execution(self, execution_id: str) -> ExecutionStatus | None:
        tracker = get_tracker()
        return tracker.get_active(execution_id) or tracker.get_completed(execution_id)

    def cancel_execution(self, execution_id: str) -> bool:
        task = self._execution_tasks.get(execution_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def _prepare_interactive_execution(
        self,
        request: InteractiveExecutionRequest,
        *,
        execution_id: str | None,
    ) -> dict[str, Any]:
        conversation_key, resume_id, question_scope_key = (
            self._resolve_execution_context(request)
        )
        execution = get_tracker().start_execution(
            conversation_key,
            execution_id=execution_id,
            channel=request.channel,
            backend=settings.agent_backend,
        )
        return {
            "conversation_key": conversation_key,
            "resume_id": resume_id,
            "question_scope_key": question_scope_key,
            "execution": execution,
        }

    def _register_execution_task(
        self,
        execution_id: str,
        task: asyncio.Task[Any],
    ) -> None:
        self._execution_tasks[execution_id] = task

        def _cleanup(done_task: asyncio.Task[Any]) -> None:
            self._execution_tasks.pop(execution_id, None)
            if not done_task.cancelled():
                return
            execution = get_tracker().get_active(execution_id)
            if execution is None or execution.status != "running":
                return
            elapsed_ms = int((time.time() - execution.started_at) * 1000)
            execution.mark_cancelled("Execution cancelled", elapsed_ms)
            get_tracker().finish_execution(execution_id)

        task.add_done_callback(_cleanup)

    def _bind_current_task(self, execution_id: str) -> None:
        task = asyncio.current_task()
        if task is None:
            return
        if self._execution_tasks.get(execution_id) is task:
            return
        self._register_execution_task(execution_id, task)

    async def _run_interactive_prepared(
        self,
        request: InteractiveExecutionRequest,
        *,
        prepared: dict[str, Any],
    ) -> AgentResult | None:
        conversation_key = prepared["conversation_key"]
        resume_id = prepared["resume_id"]
        question_scope_key = prepared["question_scope_key"]
        execution: ExecutionStatus = prepared["execution"]
        started_at = time.monotonic()
        lock_key = request.chat_key or conversation_key
        tracker = get_tracker()
        assert lock_key is not None
        async with self._lock_for(lock_key):
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
                    role=request.stored_role,
                    content=self._stored_user_content(
                        request.message,
                        request.attachments,
                        stored_message=request.stored_message,
                    ),
                    sdk_session_id=resume_id,
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
            except asyncio.CancelledError:
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                execution.mark_cancelled("Execution cancelled", elapsed_ms)
                tracker.finish_execution(execution.execution_id)
                logger.info(
                    "Agent turn cancelled: channel={}, conversation_key={}, execution_id={}",
                    request.channel or "unknown",
                    conversation_key,
                    execution.execution_id,
                )
                raise
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
                    except asyncio.CancelledError:
                        elapsed_ms = int((time.monotonic() - started_at) * 1000)
                        execution.mark_cancelled("Execution cancelled", elapsed_ms)
                        tracker.finish_execution(execution.execution_id)
                        logger.info(
                            "Agent turn cancelled after retry: channel={}, conversation_key={}, execution_id={}",
                            request.channel or "unknown",
                            conversation_key,
                            execution.execution_id,
                        )
                        raise
                    except Exception:
                        logger.exception(
                            "Agent turn failed after retry: conversation_key={}",
                            conversation_key,
                        )
                        elapsed_ms = int((time.monotonic() - started_at) * 1000)
                        execution.mark_failed(
                            "Agent turn failed after retry",
                            elapsed_ms,
                        )
                        tracker.finish_execution(execution.execution_id)
                        return None
                else:
                    logger.exception(
                        "Agent turn failed: conversation_key={}",
                        conversation_key,
                    )
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    execution.mark_failed("Agent turn failed", elapsed_ms)
                    tracker.finish_execution(execution.execution_id)
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
            tracker.finish_execution(execution.execution_id)
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
        execution: ExecutionStatus,
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
        except asyncio.CancelledError:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            execution.mark_cancelled("Execution cancelled", elapsed_ms)
            tracker.finish_execution(execution.execution_id)
            raise
        except Exception:
            logger.exception("Background turn failed: name={}", request.name)
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            execution.mark_failed("Background turn failed", elapsed_ms)
            tracker.finish_execution(execution.execution_id)
            raise

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        execution.mark_completed(result.text, elapsed_ms)
        tracker.finish_execution(execution.execution_id)
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
        resume_id = record.sdk_session_id if record is not None else None
        if resume_id == PENDING_SDK_SESSION_ID:
            resume_id = None
        return (
            conversation_key,
            resume_id,
            conversation_key,
        )

    @staticmethod
    def _stored_user_content(
        message: str,
        attachments,
        *,
        stored_message: str | None = None,
    ) -> str:
        if stored_message is not None:
            return stored_message
        if not attachments:
            return message
        names = ", ".join(att.filename for att in attachments)
        return (
            f"{message}\n[Attachments: {names}]"
            if message
            else f"[Attachments: {names}]"
        )
