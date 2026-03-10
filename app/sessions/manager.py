from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from loguru import logger

from app.config import settings
from app.sessions.store import TELEGRAM_PENDING_NEW, SessionRecord, SessionStore

# Callback that sends rendered question widgets to the user's channel.
SendQuestionCallback = Callable[[list[dict]], Awaitable[None]]

# Timeout for waiting on user answers (seconds).
_QUESTION_TIMEOUT = 300


@dataclass
class PendingQuestion:
    """Tracks an in-flight AskUserQuestion awaiting user reply."""

    questions: list[dict]
    future: asyncio.Future[str] = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )


@dataclass(frozen=True)
class TelegramSessionContext:
    conversation_key: str
    resume_session_id: str | None = None


# Session reset thresholds
IDLE_TIMEOUT_HOURS = 4
DAILY_RESET_HOUR = 4  # 4 AM in configured timezone


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

    async def reset_telegram_session(self, session_key: str) -> str | None:
        """Force reset the Telegram session. Returns confirmation text."""
        self._pending_questions.pop(session_key, None)
        self._store.mark_telegram_session_reset(session_key)
        logger.info("Telegram session force reset via /new: chat_key={}", session_key)
        return "Session reset. Starting fresh."

    def resolve_telegram_session(self, chat_key: str) -> TelegramSessionContext:
        conversation_key = self._store.get_active_telegram_conversation(chat_key)
        if conversation_key == TELEGRAM_PENDING_NEW:
            return self._create_telegram_conversation(chat_key)
        if conversation_key is not None:
            record = self._store.get(conversation_key)
            if record is None:
                return TelegramSessionContext(conversation_key=conversation_key)
            if self.should_resume_telegram(record):
                logger.debug(
                    "Telegram session resumed: chat_key={}, conversation_key={}, sdk_session_id={}",
                    chat_key,
                    conversation_key,
                    record.sdk_session_id,
                )
                return TelegramSessionContext(
                    conversation_key=conversation_key,
                    resume_session_id=record.sdk_session_id,
                )

            reason = self.telegram_reset_reason(record)
            logger.info(
                "Telegram session reset: chat_key={}, conversation_key={}, reason={}",
                chat_key,
                conversation_key,
                reason,
            )
            return self._create_telegram_conversation(chat_key)

        legacy_record = self._store.get(chat_key)
        if legacy_record is not None:
            if self.should_resume_telegram(legacy_record):
                self._store.set_active_telegram_conversation(chat_key, chat_key)
                logger.debug(
                    "Telegram legacy session adopted: chat_key={}, sdk_session_id={}",
                    chat_key,
                    legacy_record.sdk_session_id,
                )
                return TelegramSessionContext(
                    conversation_key=chat_key,
                    resume_session_id=legacy_record.sdk_session_id,
                )

            reason = self.telegram_reset_reason(legacy_record)
            logger.info(
                "Telegram legacy session expired: chat_key={}, reason={}",
                chat_key,
                reason,
            )
            return self._create_telegram_conversation(chat_key)

        return self._create_telegram_conversation(chat_key)

    def should_resume_telegram(self, record: SessionRecord) -> bool:
        return not _needs_reset(record.created_at) and not _is_idle(record.last_active)

    def telegram_reset_reason(self, record: SessionRecord) -> str:
        return "daily_reset" if _needs_reset(record.created_at) else "idle_timeout"

    def register_pending_question(
        self,
        session_key: str,
        questions: list[dict],
    ) -> asyncio.Future[str]:
        loop = asyncio.get_running_loop()
        pq = PendingQuestion(questions=questions, future=loop.create_future())
        self._pending_questions[session_key] = pq
        return pq.future

    def resolve_pending_question(self, session_key: str, text: str) -> bool:
        return self.answer_question(session_key, text)

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

    def build_question_handler(
        self,
        session_key: str,
        send_question: SendQuestionCallback | None,
    ):
        if send_question is None:
            return None

        async def on_question(questions: list[dict]) -> dict[str, str]:
            future = self.register_pending_question(session_key, questions)
            try:
                await send_question(questions)
                raw_reply: str = await asyncio.wait_for(
                    future, timeout=_QUESTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning("AskUserQuestion timed out: session_key={}", session_key)
                return {}
            finally:
                self._pending_questions.pop(session_key, None)
            return self._parse_answer(raw_reply, questions)

        return on_question

    @staticmethod
    def _new_telegram_conversation_key(chat_key: str) -> str:
        suffix = chat_key.removeprefix("telegram:chat:")
        suffix = suffix if suffix != chat_key else chat_key.replace(":", "_")
        return f"telegram:conversation:{suffix}:{uuid4().hex[:12]}"

    def _create_telegram_conversation(self, chat_key: str) -> TelegramSessionContext:
        conversation_key = self._new_telegram_conversation_key(chat_key)
        self._store.set_active_telegram_conversation(chat_key, conversation_key)
        logger.info(
            "Telegram conversation created: chat_key={}, conversation_key={}",
            chat_key,
            conversation_key,
        )
        return TelegramSessionContext(conversation_key=conversation_key)
