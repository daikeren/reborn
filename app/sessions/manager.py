from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

from app.agent.runtime import AgentResult, agent_turn
from app.agent.types import Attachment
from app.config import settings
from app.monitoring.tracker import get_tracker
from app.monitoring.types import ExecutionEvent, ExecutionEventKind
from app.sessions.store import SessionStore

# Callback that sends rendered question widgets to the user's channel.
SendQuestionCallback = Callable[[list[dict]], Awaitable[None]]

# Timeout for waiting on user answers (seconds).
_QUESTION_TIMEOUT = 300


@dataclass
class PendingQuestion:
    """Tracks an in-flight AskUserQuestion awaiting user reply."""
    questions: list[dict]
    future: asyncio.Future[str] = field(default_factory=lambda: asyncio.get_event_loop().create_future())

# Session reset thresholds
IDLE_TIMEOUT_HOURS = 4
DAILY_RESET_HOUR = 4  # 4 AM in configured timezone

# Event dedup: bounded set with TTL
_seen_events: dict[str, float] = {}
_DEDUP_TTL = 300  # 5 minutes


def _is_duplicate(event_id: str) -> bool:
    """Check if event_id was already processed. Cleans expired entries."""
    now = time.monotonic()
    # Clean expired
    expired = [k for k, v in _seen_events.items() if now - v > _DEDUP_TTL]
    for k in expired:
        del _seen_events[k]
    if event_id in _seen_events:
        return True
    _seen_events[event_id] = now
    return False


def _needs_reset(created_at: str) -> bool:
    """Check if a Telegram session should be reset (daily at 4am or idle 4h)."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    try:
        created = datetime.fromisoformat(created_at).astimezone(tz)
    except (ValueError, TypeError):
        return True

    # Daily reset: if session was created before today's reset hour
    today_reset = now.replace(hour=DAILY_RESET_HOUR, minute=0, second=0, microsecond=0)
    if now >= today_reset and created < today_reset:
        return True

    return False


def _is_idle(last_active: str) -> bool:
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    try:
        last = datetime.fromisoformat(last_active).astimezone(tz)
    except (ValueError, TypeError):
        return True
    return (now - last) > timedelta(hours=IDLE_TIMEOUT_HOURS)


class SessionManager:
    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._pending_questions: dict[str, PendingQuestion] = {}

    # ------------------------------------------------------------------
    # Public helpers for pending-question state
    # ------------------------------------------------------------------

    def has_pending_question(self, session_key: str) -> bool:
        return session_key in self._pending_questions

    def answer_question(self, session_key: str, text: str) -> bool:
        """Resolve a pending question's future with *text*. Returns True if resolved."""
        pq = self._pending_questions.get(session_key)
        if pq is None or pq.future.done():
            return False
        pq.future.set_result(text)
        return True

    async def handle_telegram(
        self,
        update_id: int,
        text: str,
        *,
        attachments: list[Attachment] | None = None,
        send_question: SendQuestionCallback | None = None,
    ) -> str | None:
        """Process a Telegram message. Returns reply text or None."""
        event_id = f"tg:{update_id}"
        if _is_duplicate(event_id):
            logger.debug("Duplicate Telegram event ignored: {}", event_id)
            return None

        session_key = "telegram:dm"
        record = self._store.get(session_key)
        logger.debug(
            "Telegram message received: update_id={}, text_len={}, attachments={}, has_session={}",
            update_id,
            len(text),
            len(attachments) if attachments else 0,
            record is not None,
        )

        # Check if we need a fresh session
        resume_id: str | None = None
        if record:
            needs_daily_reset = _needs_reset(record.created_at)
            idle_timeout_hit = _is_idle(record.last_active)
            if not needs_daily_reset and not idle_timeout_hit:
                resume_id = record.sdk_session_id
                logger.debug(
                    "Telegram session resumed: session_key={}, sdk_session_id={}",
                    session_key,
                    resume_id,
                )
            else:
                self._store.delete(session_key)
                reason = "daily_reset" if needs_daily_reset else "idle_timeout"
                logger.info(
                    "Telegram session reset: session_key={}, reason={}",
                    session_key,
                    reason,
                )

        result = await self._run_agent(
            session_key, text, resume_id=resume_id, channel="telegram",
            attachments=attachments, send_question=send_question,
        )
        if result is None:
            logger.warning("Telegram agent returned no result: update_id={}", update_id)
            return None
        logger.debug(
            "Telegram reply generated: update_id={}, reply_len={}",
            update_id,
            len(result.text),
        )
        return result.text if result else None

    async def handle_slack(
        self,
        event_id: str,
        channel_id: str,
        thread_ts: str | None,
        text: str,
        *,
        attachments: list[Attachment] | None = None,
        send_question: SendQuestionCallback | None = None,
    ) -> str | None:
        """Process a Slack message. Returns reply text or None."""
        dedup_key = f"slack:{event_id}"
        if _is_duplicate(dedup_key):
            logger.debug("Duplicate Slack event ignored: {}", event_id)
            return None

        session_key = f"slack:thread:{channel_id}:{thread_ts}"

        record = self._store.get(session_key)
        resume_id = record.sdk_session_id if record else None
        logger.debug(
            "Slack message received: event_id={}, channel_id={}, thread_ts={}, text_len={}, attachments={}, has_session={}",
            event_id,
            channel_id,
            thread_ts,
            len(text),
            len(attachments) if attachments else 0,
            record is not None,
        )
        if resume_id:
            logger.debug(
                "Slack session resumed: session_key={}, sdk_session_id={}",
                session_key,
                resume_id,
            )

        result = await self._run_agent(
            session_key, text, resume_id=resume_id, channel="slack",
            attachments=attachments, send_question=send_question,
        )
        if result is None:
            logger.warning("Slack agent returned no result: event_id={}", event_id)
            return None
        logger.debug(
            "Slack reply generated: event_id={}, reply_len={}",
            event_id,
            len(result.text),
        )
        return result.text if result else None

    async def reset_telegram_session(self) -> str | None:
        """Force reset the Telegram session. Returns confirmation text."""
        self._store.delete("telegram:dm")
        logger.info("Telegram session force reset via /new")
        return "Session reset. Starting fresh."

    def _parse_answer(self, reply: str, questions: list[dict]) -> dict[str, str]:
        """Parse a raw text reply into a {question_text: answer} mapping."""
        answers: dict[str, str] = {}
        lines = [l.strip() for l in reply.splitlines() if l.strip()]  # noqa: E741

        for idx, q in enumerate(questions):
            question_text = q.get("question", "")
            options = q.get("options", [])
            raw = lines[idx] if idx < len(lines) else reply

            # Try numeric index (1-based)
            try:
                opt_idx = int(raw) - 1
                if 0 <= opt_idx < len(options):
                    answers[question_text] = options[opt_idx].get("label", raw)
                    continue
            except (ValueError, TypeError):
                pass

            # Try case-insensitive label match
            matched = False
            for opt in options:
                if opt.get("label", "").lower() == raw.lower():
                    answers[question_text] = opt["label"]
                    matched = True
                    break
            if not matched:
                answers[question_text] = raw

        return answers

    async def _run_agent(
        self,
        session_key: str,
        message: str,
        *,
        resume_id: str | None = None,
        channel: str | None = None,
        attachments: list[Attachment] | None = None,
        send_question: SendQuestionCallback | None = None,
    ) -> AgentResult | None:
        """Run agent_turn with retry on resume failure."""
        started_at = time.monotonic()
        logger.info(
            "Agent turn started: channel={}, session_key={}, resume={}, attachments={}",
            channel or "unknown",
            session_key,
            resume_id is not None,
            len(attachments) if attachments else 0,
        )

        # Build stored content with attachment note
        stored_content = message
        if attachments:
            names = ", ".join(a.filename for a in attachments)
            stored_content = f"{message}\n[Attachments: {names}]" if message else f"[Attachments: {names}]"

        self._store.append_message(
            session_key=session_key,
            role="user",
            content=stored_content,
            sdk_session_id=resume_id,
        )

        # Set up execution tracking
        tracker = get_tracker()
        backend_name = settings.agent_backend
        execution = tracker.start_execution(
            session_key, channel=channel, backend=backend_name,
        )

        async def _on_event(event: ExecutionEvent) -> None:
            execution.add_event(event)
            if event.kind == ExecutionEventKind.TOOL_USE:
                tool = event.data.get("tool", "unknown")
                if tool not in execution.tools_used:
                    execution.tools_used.append(tool)
            elif event.kind == ExecutionEventKind.TURN_COMPLETED:
                execution.current_turn += 1

        # Build on_question closure if a send_question callback was provided
        on_question = None
        if send_question:
            async def on_question(questions: list[dict]) -> dict[str, str]:
                await send_question(questions)
                loop = asyncio.get_running_loop()
                pq = PendingQuestion(questions=questions, future=loop.create_future())
                self._pending_questions[session_key] = pq
                try:
                    raw_reply: str = await asyncio.wait_for(pq.future, timeout=_QUESTION_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning("AskUserQuestion timed out: session_key={}", session_key)
                    return {}
                finally:
                    self._pending_questions.pop(session_key, None)
                return self._parse_answer(raw_reply, questions)

        try:
            result = await agent_turn(
                message, session_id=resume_id, enable_skills=True, channel=channel,
                attachments=attachments, on_event=_on_event, on_question=on_question,
            )
        except Exception:
            if resume_id is not None:
                logger.warning(
                    "Resume failed, falling back to new session: session_key={}",
                    session_key,
                )
                try:
                    result = await agent_turn(
                        message, session_id=None, enable_skills=True, channel=channel,
                        attachments=attachments, on_event=_on_event, on_question=on_question,
                    )
                except Exception:
                    logger.exception("Agent turn failed after retry: session_key={}", session_key)
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    execution.mark_failed("Agent turn failed after retry", elapsed_ms)
                    tracker.finish_execution(session_key)
                    return None
            else:
                logger.exception("Agent turn failed: session_key={}", session_key)
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                execution.mark_failed("Agent turn failed", elapsed_ms)
                tracker.finish_execution(session_key)
                return None

        if result.session_id:
            self._store.upsert(session_key, result.session_id)
            count = self._store.increment_message_count(session_key)
            if count > 0 and count % 100 == 0:
                logger.warning(
                    "Session message_count milestone: session_key={}, count={}",
                    session_key,
                    count,
                )

        if result.text:
            self._store.append_message(
                session_key=session_key,
                role="assistant",
                content=result.text,
                sdk_session_id=result.session_id or resume_id,
            )

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        execution.mark_completed(result.text, elapsed_ms)
        tracker.finish_execution(session_key)
        logger.info(
            "Agent turn completed: channel={}, session_key={}, elapsed_ms={}, reply_len={}, has_session_id={}",
            channel or "unknown",
            session_key,
            elapsed_ms,
            len(result.text),
            result.session_id is not None,
        )
        return result
