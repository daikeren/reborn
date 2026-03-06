from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from app.agent.backends.base import DEFAULT_TOOLS
from app.agent.codex_client import CodexAppServerClient, CodexClientError
from app.agent.skills import filter_available_skill_rows
from app.agent.system_prompt import build_system_prompt
from app.agent.types import AgentError, AgentResult, Attachment
from app.config import settings
from app.mcp.memory import memory_server_config
from app.monitoring.types import EventCallback, ExecutionEventKind, make_event

logger = logging.getLogger(__name__)


class CodexBackend:
    name = "codex"
    _MAX_LINE_LEN = 2000
    _FINAL_CHANNEL = "final"

    def create_client(self) -> CodexAppServerClient:
        return CodexAppServerClient()

    def _build_mcp_servers(self, mcp_servers: dict[str, Any] | None) -> dict[str, Any]:
        servers: dict[str, Any] = {"memory": memory_server_config()}
        if mcp_servers:
            servers.update(mcp_servers)
        return servers

    def _build_sandbox_policy(self) -> dict[str, Any]:
        writable_roots = [
            str(root)
            for root in (settings.workspace_dir, *settings.extra_writable_roots)
        ]
        return {
            "type": "workspaceWrite",
            "networkAccess": True,
            "writableRoots": writable_roots,
        }

    def _allowed_tools_hint(
        self, allowed_tools: list[str] | None, max_turns: int
    ) -> str:
        if allowed_tools is None:
            return ""
        tools = ", ".join(allowed_tools) if allowed_tools else "(none)"
        return (
            "\n\n## Runtime Constraints\n"
            f"- Preferred tools: {tools}\n"
            f"- Max turns hint: {max_turns}\n"
            "- Treat this as hard policy unless user explicitly overrides."
        )

    def _wrap_long_lines(self, text: str, max_line_len: int | None = None) -> str:
        """Hard-wrap very long single lines to avoid upstream chunk splitter limits."""
        limit = max_line_len or self._MAX_LINE_LEN
        if limit <= 0:
            return text

        wrapped: list[str] = []
        for line in text.splitlines(keepends=True):
            has_newline = line.endswith("\n")
            body = line[:-1] if has_newline else line

            if len(body) <= limit:
                wrapped.append(line)
                continue

            chunk = body
            while len(chunk) > limit:
                wrapped.append(chunk[:limit] + "\n")
                chunk = chunk[limit:]
            if chunk:
                wrapped.append(chunk)
            if has_newline:
                wrapped.append("\n")

        if not wrapped and text:
            # splitlines() returns [] for some edge cases; keep original text.
            return text
        return "".join(wrapped)

    def _extract_channel(self, payload: dict[str, Any]) -> str | None:
        channel = payload.get("channel")
        if isinstance(channel, str):
            return channel

        item = payload.get("item")
        if isinstance(item, dict):
            item_channel = item.get("channel")
            if isinstance(item_channel, str):
                return item_channel
            message = item.get("message")
            if isinstance(message, dict):
                message_channel = message.get("channel")
                if isinstance(message_channel, str):
                    return message_channel

        return None

    def _is_final_channel(self, payload: dict[str, Any]) -> bool:
        channel = self._extract_channel(payload)
        return channel is None or channel == self._FINAL_CHANNEL

    async def _skill_inputs(
        self, client: CodexAppServerClient
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        skills = await client.list_skills(cwd=str(settings.workspace_dir))
        skills = filter_available_skill_rows(skills)
        skill_inputs: list[dict[str, str]] = []
        skill_descriptions: dict[str, str] = {}
        for skill in skills:
            name = skill.get("name")
            path = skill.get("path")
            description = skill.get("description", "")
            if not isinstance(name, str) or not isinstance(path, str):
                continue
            skill_inputs.append({"type": "skill", "name": name, "path": path})
            skill_descriptions[name] = (
                description if isinstance(description, str) else ""
            )
        return skill_inputs, skill_descriptions

    def _build_attachment_items(
        self, attachments: list[Attachment] | None
    ) -> list[dict[str, str]]:
        if not attachments:
            return []

        items: list[dict[str, str]] = []
        for att in attachments:
            if att.is_image:
                b64 = base64.b64encode(att.data).decode()
                data_uri = f"data:{att.mime_type};base64,{b64}"
                items.append({"type": "image_url", "image_url": data_uri})
            else:
                extracted = att.extract_text()
                if extracted:
                    items.append(
                        {
                            "type": "text",
                            "text": f"[Content of {att.filename}]\n{extracted}",
                        }
                    )
                else:
                    items.append(
                        {
                            "type": "text",
                            "text": f"[Attached file: {att.filename} ({att.mime_type}) — content could not be extracted]",
                        }
                    )
        return items

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
        on_question: object | None = None,  # accepted for protocol compliance; unused
    ) -> AgentResult:
        model = model or settings.chat_model
        tools = allowed_tools if allowed_tools is not None else DEFAULT_TOOLS
        servers = self._build_mcp_servers(mcp_servers)
        sandbox_policy = self._build_sandbox_policy()

        async with self.create_client() as client:
            skill_inputs: list[dict[str, str]] = []
            skill_descriptions: dict[str, str] | None = None
            if enable_skills:
                skill_inputs, skill_descriptions = await self._skill_inputs(client)

            system_prompt = build_system_prompt(
                skills=skill_descriptions,
                channel=channel,
            ) + self._allowed_tools_hint(tools, max_turns)
            safe_system_prompt = self._wrap_long_lines(system_prompt)
            safe_message = self._wrap_long_lines(message)

            config = {"mcp_servers": servers}
            cwd = str(Path(settings.workspace_dir).parent)

            try:
                if session_id:
                    thread_id = await client.resume_thread(
                        thread_id=session_id,
                        cwd=cwd,
                        model=model,
                        developer_instructions=safe_system_prompt,
                        config=config,
                    )
                else:
                    thread_id = await client.start_thread(
                        cwd=cwd,
                        model=model,
                        developer_instructions=safe_system_prompt,
                        config=config,
                    )
            except Exception as exc:
                raise AgentError(f"Failed to start Codex thread: {exc}") from exc

            input_items: list[dict[str, str]] = [{"type": "text", "text": safe_message}]
            attachment_items = self._build_attachment_items(attachments)
            if attachment_items:
                input_items.extend(attachment_items)
            if skill_inputs:
                input_items.extend(skill_inputs)

            latest_final_text: str | None = None
            final_messages_seen = 0
            result_session_id: str | None = thread_id
            _compacted = False

            for _attempt in range(2):
                latest_final_text = None
                final_messages_seen = 0
                _context_window_exceeded = False

                try:
                    async for note in client.stream_turn(
                        thread_id=thread_id,
                        input_items=input_items,
                        model=model,
                        sandbox_policy=sandbox_policy,
                    ):
                        if note.method in ("context_compacted", "thread/compacted"):
                            logger.info(
                                "Codex compact notification: %s (thread=%s)",
                                note.method,
                                thread_id,
                            )
                            continue

                        if note.method == "item/completed":
                            item = note.params.get("item", {})
                            item_type = (
                                item.get("type") if isinstance(item, dict) else None
                            )

                            if item_type == "contextCompaction":
                                logger.info(
                                    "Codex context compaction item (thread=%s)",
                                    thread_id,
                                )
                                continue

                            if item_type == "toolUse" and on_event:
                                tool_name = item.get("name", "unknown")
                                tool_input = str(item.get("input", ""))
                                await on_event(
                                    make_event(
                                        ExecutionEventKind.TOOL_USE,
                                        tool=tool_name,
                                        input=tool_input,
                                    )
                                )
                            elif item_type == "toolResult" and on_event:
                                tool_output = str(item.get("output", ""))
                                await on_event(
                                    make_event(
                                        ExecutionEventKind.TOOL_RESULT,
                                        output=tool_output,
                                    )
                                )
                            elif item_type == "agentMessage":
                                is_final = self._is_final_channel(note.params)
                                text = (
                                    item.get("text") if isinstance(item, dict) else None
                                )
                                if is_final and isinstance(text, str):
                                    latest_final_text = text
                                    final_messages_seen += 1
                                    if on_event:
                                        await on_event(
                                            make_event(
                                                ExecutionEventKind.TEXT_CHUNK, text=text
                                            )
                                        )
                                elif not is_final and on_event:
                                    commentary_text = (
                                        text if isinstance(text, str) else ""
                                    )
                                    await on_event(
                                        make_event(
                                            ExecutionEventKind.COMMENTARY,
                                            text=commentary_text,
                                        )
                                    )
                            continue

                        if note.method == "turn/completed":
                            if on_event:
                                await on_event(
                                    make_event(ExecutionEventKind.TURN_COMPLETED)
                                )
                            turn = note.params.get("turn", {})
                            if (
                                isinstance(turn, dict)
                                and turn.get("status") == "failed"
                            ):
                                error = turn.get("error", "")
                                if (
                                    "contextWindowExceeded" in str(error)
                                    and not _compacted
                                ):
                                    _context_window_exceeded = True
                                else:
                                    raise AgentError(f"Codex turn failed: {error}")
                except (CodexClientError, AgentError):
                    if latest_final_text is not None and result_session_id:
                        logger.warning(
                            "Agent turn partially failed; returning partial output"
                        )
                        return AgentResult(
                            text=latest_final_text, session_id=result_session_id
                        )
                    raise
                except Exception as exc:
                    if latest_final_text is not None and result_session_id:
                        logger.warning(
                            "Agent turn partially failed: %s", exc, exc_info=True
                        )
                        return AgentResult(
                            text=latest_final_text, session_id=result_session_id
                        )
                    raise AgentError(f"Agent call failed: {exc}") from exc

                if _context_window_exceeded:
                    logger.info(
                        "Context window exceeded on thread %s; compacting and retrying",
                        thread_id,
                    )
                    try:
                        await client.compact_thread(thread_id=thread_id)
                    except Exception as exc:
                        raise AgentError(
                            f"Context window exceeded and compaction failed: {exc}"
                        ) from exc
                    _compacted = True
                    continue
                break

        dropped_intermediate = max(final_messages_seen - 1, 0)
        selected_final_len = (
            len(latest_final_text) if latest_final_text is not None else 0
        )
        if final_messages_seen > 1:
            logger.warning(
                "Codex turn emitted multiple final messages; using latest: final_messages_seen=%s, "
                "dropped_intermediate_final_messages=%s, selected_final_len=%s",
                final_messages_seen,
                dropped_intermediate,
                selected_final_len,
            )
        else:
            logger.info(
                "Codex turn final message stats: final_messages_seen=%s, "
                "dropped_intermediate_final_messages=%s, selected_final_len=%s",
                final_messages_seen,
                dropped_intermediate,
                selected_final_len,
            )

        final_text = latest_final_text if latest_final_text is not None else ""
        return AgentResult(text=final_text, session_id=result_session_id)
