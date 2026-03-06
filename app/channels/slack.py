from __future__ import annotations

import re

import aiohttp
from loguru import logger
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from app.agent.types import Attachment
from app.auth import verify_slack
from app.orchestrator import (
    ExecutionService,
    InteractiveExecutionRequest,
    is_duplicate_event,
)
from app.sessions.manager import SessionManager


def create_slack_app(
    bot_token: str,
    app_token: str,
    session_manager: SessionManager,
    execution_service: ExecutionService,
) -> tuple[AsyncApp, AsyncSocketModeHandler]:
    """Build and return a Slack Bolt async app + Socket Mode handler."""

    app = AsyncApp(token=bot_token)

    @app.event("message")
    async def handle_message(event: dict, say, client) -> None:  # noqa: ANN001
        if not verify_slack(event):
            logger.debug(
                "Ignoring Slack event: user={}, subtype={}, has_bot_id={}",
                event.get("user"),
                event.get("subtype"),
                bool(event.get("bot_id")),
            )
            return

        text = event.get("text", "")

        # Download attached files
        attachments: list[Attachment] = []
        files = event.get("files", [])
        if files:
            token = client.token
            async with aiohttp.ClientSession() as http:
                for f in files:
                    url = f.get("url_private_download")
                    mime = f.get("mimetype", "application/octet-stream")
                    name = f.get("name", "file")
                    if not url:
                        continue
                    try:
                        async with http.get(
                            url, headers={"Authorization": f"Bearer {token}"}
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                attachments.append(
                                    Attachment(
                                        filename=name,
                                        mime_type=mime,
                                        data=data,
                                    )
                                )
                            else:
                                logger.warning(
                                    "Failed to download Slack file: name={}, status={}",
                                    name,
                                    resp.status,
                                )
                    except Exception:
                        logger.opt(exception=True).warning(
                            "Error downloading Slack file: name={}",
                            name,
                        )

        if not text and not attachments:
            logger.debug("Ignoring Slack event with no text or attachments")
            return

        # Use event_id from envelope if available, fall back to client_msg_id, then ts
        event_id = (
            event.get("event_id") or event.get("client_msg_id") or event.get("ts", "")
        )
        channel_id = event.get("channel", "")
        thread_ts = event.get("thread_ts")  # None if top-level message
        msg_ts = event.get("ts", "")
        reply_thread_ts = thread_ts or msg_ts

        dedup_key = f"slack:{event_id}"
        if is_duplicate_event(dedup_key):
            logger.debug("Duplicate Slack event ignored: {}", event_id)
            return

        # If there's a pending question for this thread, resolve it with the reply
        session_key = f"slack:thread:{channel_id}:{thread_ts or msg_ts}"
        if session_manager.has_pending_question(session_key):
            session_manager.answer_question(session_key, text)
            return

        logger.info(
            "Slack message received: event_id={}, channel_id={}, thread_ts={}, text_len={}",
            event_id,
            channel_id,
            thread_ts,
            len(text),
        )

        # React with 👀 immediately
        try:
            await client.reactions_add(
                name="eyes",
                channel=channel_id,
                timestamp=msg_ts,
            )
        except Exception:
            logger.opt(exception=True).warning(
                "Failed to add Slack reaction: event_id={}, channel_id={}, msg_ts={}",
                event_id,
                channel_id,
                msg_ts,
            )

        # Build send_question callback for AskUserQuestion rendering
        async def send_question(questions: list[dict]) -> None:
            blocks: list[dict] = []
            for i, q in enumerate(questions):
                header = q.get("header", "")
                question_text = q.get("question", "")
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{header}*: {question_text}",
                        },
                    }
                )
                buttons = [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": opt.get("label", "")},
                        "value": opt.get("label", ""),
                        "action_id": f"ask_user_{i}_{j}",
                    }
                    for j, opt in enumerate(q.get("options", []))
                ]
                if buttons:
                    blocks.append(
                        {
                            "type": "actions",
                            "block_id": f"ask_user_{i}",
                            "elements": buttons,
                        }
                    )
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Or type your answer in this thread.",
                        }
                    ],
                }
            )
            await client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                thread_ts=reply_thread_ts,
                text="Question",
            )

        try:
            result = await execution_service.run_interactive(
                InteractiveExecutionRequest(
                    session_key=session_key,
                    channel="slack",
                    message=text,
                    attachments=attachments or None,
                    send_question=send_question,
                )
            )
            reply = result.text if result else None
            if reply:
                await say(text=reply, thread_ts=reply_thread_ts)
                logger.info(
                    "Slack reply sent: event_id={}, reply_len={}",
                    event_id,
                    len(reply),
                )
            else:
                logger.info("Slack reply suppressed or empty: event_id={}", event_id)
        except Exception:
            logger.exception("Slack handler error: event_id={}", event_id)
        finally:
            # Remove reaction
            try:
                await client.reactions_remove(
                    name="eyes",
                    channel=channel_id,
                    timestamp=msg_ts,
                )
            except Exception:
                logger.opt(exception=True).debug(
                    "Failed to remove Slack reaction: event_id={}, channel_id={}, msg_ts={}",
                    event_id,
                    channel_id,
                    msg_ts,
                )

    @app.action(re.compile(r"^ask_user_"))
    async def handle_ask_user_action(ack, body, client) -> None:  # noqa: ANN001
        """Handle button clicks for AskUserQuestion."""
        await ack()
        action = body.get("actions", [{}])[0]
        label = action.get("value", "")
        # Determine session_key from the message context
        msg = body.get("message", {})
        ch = body.get("channel", {}).get("id", "")
        thread = msg.get("thread_ts") or msg.get("ts", "")
        sk = f"slack:thread:{ch}:{thread}"
        resolved = session_manager.answer_question(sk, label)
        logger.info(
            "Slack ask_user button clicked: action_id={}, label={}, session_key={}, resolved={}",
            action.get("action_id"),
            label,
            sk,
            resolved,
        )
        # Update the original message to show the selection and remove buttons
        try:
            await client.chat_update(
                channel=ch,
                ts=msg.get("ts", ""),
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"Selected: *{label}*"},
                    }
                ],
                text=f"Selected: {label}",
            )
        except Exception:
            logger.opt(exception=True).debug("Failed to update Slack ask_user message")

    handler = AsyncSocketModeHandler(app, app_token)
    return app, handler
