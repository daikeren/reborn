from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)
from claude_agent_sdk.types import (
    HookEvent,
    HookMatcher,
    PermissionResult,
    PermissionResultAllow,
    ToolPermissionContext,
)

from app.agent.backends.base import DEFAULT_TOOLS, QuestionCallback
from app.agent.image_fallback import (
    build_retry_instruction,
    build_text_attachment_entries,
    failed_image_attachment_names,
    has_image_attachments,
    is_recoverable_image_error,
)
from app.agent.skills import load_all_skills
from app.agent.system_prompt import build_system_prompt
from app.agent.types import AgentError, AgentResult, Attachment
from app.config import settings
from app.mcp.memory import memory_server_config
from app.monitoring.types import EventCallback, ExecutionEventKind, make_event

logger = logging.getLogger(__name__)

CLAUDE_DEFAULT_TOOLS = [*DEFAULT_TOOLS, "Bash", "Write"]


class ClaudeBackend:
    name = "claude"

    def _build_mcp_servers(self, mcp_servers: dict[str, Any] | None) -> dict[str, Any]:
        servers: dict[str, Any] = {"memory": memory_server_config()}
        if mcp_servers:
            servers.update(mcp_servers)
        return servers

    def _build_agents_and_skills(
        self, enable_skills: bool
    ) -> tuple[dict[str, AgentDefinition] | None, dict[str, str] | None]:
        if not enable_skills:
            return None, None

        loaded = load_all_skills()
        if not loaded:
            return None, None

        agents: dict[str, AgentDefinition] = {}
        descriptions: dict[str, str] = {}
        for name, defn in loaded.items():
            descriptions[name] = defn.description
            agents[name] = AgentDefinition(
                description=defn.description,
                prompt=defn.prompt,
                tools=defn.tools,
                model=defn.model,
            )
        return agents, descriptions

    def _build_content(
        self,
        message: str,
        attachments: list[Attachment] | None,
        *,
        fallback_image_retry: bool = False,
    ) -> str | list[dict[str, Any]]:
        if not attachments and not fallback_image_retry:
            return message

        blocks: list[dict[str, Any]] = []
        if fallback_image_retry:
            blocks.append({"type": "text", "text": build_retry_instruction(message)})
        for att in attachments or []:
            if att.is_image and not fallback_image_retry:
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": att.mime_type,
                            "data": base64.b64encode(att.data).decode(),
                        },
                    }
                )
        for text in build_text_attachment_entries(
            attachments,
            include_failed_images=fallback_image_retry,
        ):
            blocks.append({"type": "text", "text": text})
        if message:
            blocks.append({"type": "text", "text": message})
        return blocks or message

    def _build_can_use_tool(self, on_question: QuestionCallback) -> Any:
        """Return a can_use_tool callback that intercepts AskUserQuestion."""

        async def _can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResult:
            if tool_name == "AskUserQuestion":
                questions = tool_input.get("questions", [])
                try:
                    answers = await on_question(questions)
                except Exception:
                    logger.exception("on_question callback failed")
                    answers = {}
                # Return allow with the answers injected into updated_input
                return PermissionResultAllow(
                    updated_input={**tool_input, "answers": answers},
                )
            # All other tools: pass through unchanged
            return PermissionResultAllow(updated_input=tool_input)

        return _can_use_tool

    async def _emit_image_retry_event(
        self,
        *,
        on_event: EventCallback | None,
        error_text: str,
    ) -> None:
        if on_event:
            await on_event(
                make_event(
                    ExecutionEventKind.ERROR,
                    text="Image upload failed upstream; retrying without image bytes.",
                    recoverable=True,
                    fallback="image_text_only",
                    backend=self.name,
                    error=error_text,
                )
            )

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
    ) -> AgentResult:
        model = model or settings.chat_model
        tools = allowed_tools if allowed_tools is not None else CLAUDE_DEFAULT_TOOLS
        servers = self._build_mcp_servers(mcp_servers)

        env: dict[str, str] = {}
        if settings.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

        agents, skill_descriptions = self._build_agents_and_skills(enable_skills)
        if agents and "Task" not in tools:
            tools = [*tools, "Task"]

        # Build can_use_tool callback to intercept AskUserQuestion
        can_use_tool_cb = self._build_can_use_tool(on_question) if on_question else None

        # A PreToolUse hook on AskUserQuestion is required so the SDK sends
        # a permission request instead of auto-allowing via bypassPermissions.
        # Matching only this tool avoids "Stream closed" noise on every other
        # tool call.
        hooks: dict[HookEvent, list[HookMatcher]] | None = None
        if can_use_tool_cb:

            async def _noop_hook(input, tool_use_id, context):  # noqa: A002, ANN001
                return {}

            hooks = {
                "PreToolUse": [
                    HookMatcher(matcher="AskUserQuestion", hooks=[_noop_hook])
                ],
            }

        options = ClaudeAgentOptions(
            model=model,
            system_prompt=build_system_prompt(
                skills=skill_descriptions, channel=channel
            ),
            resume=session_id,
            allowed_tools=tools,
            mcp_servers=servers,
            permission_mode="bypassPermissions",
            max_turns=max_turns,
            env=env,
            add_dirs=[
                str(settings.workspace_dir),
                *(str(path) for path in settings.extra_writable_roots),
            ],
            agents=agents,
            can_use_tool=can_use_tool_cb,
            hooks=hooks,
        )

        content = self._build_content(message, attachments)
        resume_id = session_id
        used_image_fallback = False

        while True:

            async def _prompt_stream() -> AsyncIterator[dict]:
                yield {
                    "type": "user",
                    "session_id": "",
                    "message": {"role": "user", "content": content},
                    "parent_tool_use_id": None,
                }

            texts: list[str] = []
            result_session_id = resume_id
            result_error: str | None = None

            run_options = ClaudeAgentOptions(
                model=options.model,
                system_prompt=options.system_prompt,
                resume=resume_id,
                allowed_tools=options.allowed_tools,
                mcp_servers=options.mcp_servers,
                permission_mode=options.permission_mode,
                max_turns=options.max_turns,
                env=options.env,
                add_dirs=options.add_dirs,
                agents=options.agents,
                can_use_tool=options.can_use_tool,
                hooks=options.hooks,
            )

            try:
                async for msg in query(prompt=_prompt_stream(), options=run_options):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                texts.append(block.text)
                                if on_event:
                                    await on_event(
                                        make_event(
                                            ExecutionEventKind.TEXT_CHUNK,
                                            text=block.text,
                                        )
                                    )
                            elif isinstance(block, ThinkingBlock):
                                if on_event:
                                    text = getattr(block, "text", "") or ""
                                    await on_event(
                                        make_event(
                                            ExecutionEventKind.THINKING, text=text
                                        )
                                    )
                            elif isinstance(block, ToolUseBlock):
                                if on_event:
                                    name = getattr(block, "name", "unknown")
                                    inp = str(getattr(block, "input", ""))
                                    await on_event(
                                        make_event(
                                            ExecutionEventKind.TOOL_USE,
                                            tool=name,
                                            input=inp,
                                        )
                                    )
                            elif isinstance(block, ToolResultBlock):
                                if on_event:
                                    output = str(getattr(block, "content", ""))
                                    await on_event(
                                        make_event(
                                            ExecutionEventKind.TOOL_RESULT,
                                            output=output,
                                        )
                                    )
                    elif isinstance(msg, ResultMessage):
                        result_session_id = msg.session_id or result_session_id
                        if msg.is_error:
                            result_error = str(msg.result)
                            logger.error("Agent turn error: %s", msg.result)
                        if on_event:
                            await on_event(
                                make_event(ExecutionEventKind.TURN_COMPLETED)
                            )
                    elif isinstance(msg, SystemMessage) and msg.subtype == "init":
                        sid = msg.data.get("session_id") if msg.data else None
                        if sid:
                            result_session_id = sid
            except Exception as exc:
                if texts and result_session_id:
                    partial = "\n".join(texts)
                    logger.warning("Agent turn partially failed: %s", exc)
                    return AgentResult(text=partial, session_id=result_session_id)
                if (
                    not used_image_fallback
                    and has_image_attachments(attachments)
                    and is_recoverable_image_error(exc)
                ):
                    error_text = str(exc)
                    logger.warning(
                        "Recovering from image processing failure: backend=%s, session_id=%s, images=%s, error=%s",
                        self.name,
                        result_session_id or resume_id,
                        failed_image_attachment_names(attachments),
                        error_text,
                    )
                    await self._emit_image_retry_event(
                        on_event=on_event,
                        error_text=error_text,
                    )
                    content = self._build_content(
                        message,
                        attachments,
                        fallback_image_retry=True,
                    )
                    resume_id = result_session_id or resume_id
                    used_image_fallback = True
                    continue
                raise AgentError(f"Claude backend call failed: {exc}") from exc

            if result_error:
                if texts and result_session_id:
                    return AgentResult(
                        text="\n".join(texts), session_id=result_session_id
                    )
                if (
                    not used_image_fallback
                    and has_image_attachments(attachments)
                    and is_recoverable_image_error(result_error)
                ):
                    logger.warning(
                        "Recovering from image processing failure: backend=%s, session_id=%s, images=%s, error=%s",
                        self.name,
                        result_session_id or resume_id,
                        failed_image_attachment_names(attachments),
                        result_error,
                    )
                    await self._emit_image_retry_event(
                        on_event=on_event,
                        error_text=result_error,
                    )
                    content = self._build_content(
                        message,
                        attachments,
                        fallback_image_retry=True,
                    )
                    resume_id = result_session_id or resume_id
                    used_image_fallback = True
                    continue
                raise AgentError(f"Claude backend call failed: {result_error}")

            return AgentResult(
                text="\n".join(texts),
                session_id=result_session_id,
            )
