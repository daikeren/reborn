from __future__ import annotations

import asyncio
import contextlib

from loguru import logger
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.agent.types import Attachment
from app.auth import verify_telegram
from app.orchestrator import (
    ExecutionService,
    InteractiveExecutionRequest,
    is_duplicate_event,
)
from app.sessions.manager import SessionManager
from app.utils import send_html, split_message


async def _typing_loop(bot, chat_id: int) -> None:
    """Send typing indicator every 4 seconds until cancelled."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


def _session_key_for_chat(chat_id: int | None) -> str:
    if chat_id is None:
        return "telegram:dm"
    return f"telegram:chat:{chat_id}"


def create_telegram_app(
    token: str,
    session_manager: SessionManager,
    execution_service: ExecutionService,
) -> Application:
    """Build and return a python-telegram-bot Application (long polling)."""

    async def handle_message(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not verify_telegram(update):
            logger.debug(
                "Ignoring unauthorized Telegram update: update_id={}", update.update_id
            )
            return

        assert update.message is not None
        text = update.message.text or update.message.caption or ""
        session_key = _session_key_for_chat(update.message.chat_id)

        # Download attachments
        attachments: list[Attachment] = []
        if update.message.photo:
            # photo is a list of PhotoSize; take the largest (last)
            photo = update.message.photo[-1]
            tg_file = await photo.get_file()
            data = bytes(await tg_file.download_as_bytearray())
            attachments.append(
                Attachment(
                    filename="photo.jpg",
                    mime_type="image/jpeg",
                    data=data,
                )
            )
        if update.message.document:
            doc = update.message.document
            tg_file = await doc.get_file()
            data = bytes(await tg_file.download_as_bytearray())
            attachments.append(
                Attachment(
                    filename=doc.file_name or "document",
                    mime_type=doc.mime_type or "application/octet-stream",
                    data=data,
                )
            )

        if not text and not attachments:
            logger.debug(
                "Ignoring Telegram update with no text or attachments: update_id={}",
                update.update_id,
            )
            return

        event_id = f"tg:{update.update_id}"
        if is_duplicate_event(event_id):
            logger.debug("Duplicate Telegram event ignored: {}", event_id)
            return

        # If there's a pending question, resolve it with the reply
        if session_manager.has_pending_question(session_key):
            session_manager.answer_question(session_key, text)
            return

        chat_id = update.message.chat_id
        message_id = update.message.message_id
        logger.info(
            "Telegram message received: update_id={}, chat_id={}, message_id={}, text_len={}, attachments={}",
            update.update_id,
            chat_id,
            message_id,
            len(text),
            len(attachments),
        )

        # React with 👀 immediately
        try:
            await update.message.set_reaction([ReactionTypeEmoji(emoji="👀")])
        except Exception:
            logger.opt(exception=True).debug(
                "Failed to set Telegram reaction: update_id={}, chat_id={}, message_id={}",
                update.update_id,
                chat_id,
                message_id,
            )

        # Start typing indicator
        typing_task = asyncio.create_task(_typing_loop(context.bot, chat_id))

        # Build send_question callback for AskUserQuestion rendering
        async def send_question(questions: list[dict]) -> None:
            for i, q in enumerate(questions):
                header = q.get("header", "")
                question_text = q.get("question", "")
                keyboard_rows = [
                    [
                        InlineKeyboardButton(
                            opt.get("label", ""),
                            callback_data=f"ask_user:{i}:{j}",
                        )
                    ]
                    for j, opt in enumerate(q.get("options", []))
                ]
                msg_text = f"*{header}*: {question_text}"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg_text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard_rows),
                )

        try:
            result = await execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key=session_key,
                    channel="telegram",
                    message=text,
                    attachments=attachments or None,
                    send_question=send_question,
                    session_policy="telegram",
                )
            )
            reply = result.text if result else None
            if reply:
                for chunk in split_message(reply):
                    await send_html(update.message.reply_text, chunk)
                logger.info(
                    "Telegram reply sent: update_id={}, reply_len={}",
                    update.update_id,
                    len(reply),
                )
            else:
                logger.info(
                    "Telegram reply suppressed or empty: update_id={}", update.update_id
                )
        except Exception:
            logger.exception("Telegram handler error: update_id={}", update.update_id)
        finally:
            # Stop typing indicator
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task

            # Remove reaction
            try:
                await context.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=message_id,
                    reaction=[],
                )
            except Exception:
                logger.opt(exception=True).debug(
                    "Failed to remove Telegram reaction: update_id={}, chat_id={}, message_id={}",
                    update.update_id,
                    chat_id,
                    message_id,
                )

    async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not verify_telegram(update):
            logger.debug(
                "Ignoring unauthorized /new command: update_id={}", update.update_id
            )
            return
        assert update.message is not None
        session_key = _session_key_for_chat(update.message.chat_id)
        reply = await session_manager.reset_telegram_session(session_key)
        if reply:
            await update.message.reply_text(reply)
            logger.info("Handled /new command: update_id={}", update.update_id)

    async def handle_ask_user_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses for AskUserQuestion."""
        query = update.callback_query
        if query is None:
            return
        try:
            await query.answer()
        except Exception:
            logger.opt(exception=True).debug("Failed to ack callback query")

        data = query.data or ""
        # Format: "ask_user:{question_idx}:{option_idx}"
        parts = data.split(":")
        if len(parts) != 3:
            return

        _, q_idx_str, o_idx_str = parts
        # Look up the option label from the pending question
        chat = update.effective_chat
        chat_id = chat.id if chat is not None else None
        session_key = _session_key_for_chat(chat_id)
        pq = session_manager._pending_questions.get(session_key)
        if pq is None:
            return
        try:
            q_idx = int(q_idx_str)
            o_idx = int(o_idx_str)
            label = pq.questions[q_idx]["options"][o_idx].get("label", "")
        except (IndexError, KeyError, ValueError):
            label = data

        resolved = session_manager.answer_question(session_key, label)
        logger.info(
            "Telegram ask_user button pressed: data={}, label={}, resolved={}",
            data,
            label,
            resolved,
        )
        # Edit the message to show selection
        try:
            await query.edit_message_text(f"Selected: *{label}*", parse_mode="Markdown")
        except Exception:
            logger.opt(exception=True).debug("Failed to edit Telegram ask_user message")

    # concurrent_updates is required so that CallbackQueryHandler (button
    # presses) can run while handle_message is awaiting an AskUserQuestion
    # Future.  Without it the two updates deadlock in the sequential queue.
    app = Application.builder().token(token).concurrent_updates(True).build()
    app.add_handler(CommandHandler("new", handle_new))
    app.add_handler(
        CallbackQueryHandler(handle_ask_user_callback, pattern=r"^ask_user:")
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
            handle_message,
        )
    )
    return app
