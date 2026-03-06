from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class CodexClientError(Exception):
    pass


@dataclass(frozen=True)
class CodexNotification:
    method: str
    params: dict[str, Any]


class CodexAppServerClient:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._queued_notifications: list[dict[str, Any]] = []
        self._pending_responses: dict[int, dict[str, Any]] = {}
        self._stderr_task: asyncio.Task[None] | None = None
        self._timeout = settings.codex_rpc_timeout_seconds

    async def __aenter__(self) -> "CodexAppServerClient":
        cmd = list(settings.codex_app_server_command)
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=settings.codex_rpc_stream_limit_bytes,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

    async def initialize(self) -> None:
        await self._request(
            "initialize",
            {"clientInfo": {"name": "reborn", "version": "0.1.0"}},
        )
        await self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    async def start_thread(
        self,
        *,
        cwd: str,
        model: str,
        developer_instructions: str,
        config: dict[str, Any] | None,
    ) -> str:
        result = await self._request(
            "thread/start",
            {
                "cwd": cwd,
                "model": model,
                "sandbox": settings.codex_sandbox_mode,
                "approvalPolicy": settings.codex_approval_policy,
                "developerInstructions": developer_instructions,
                "config": config,
            },
        )
        return result["thread"]["id"]

    async def resume_thread(
        self,
        *,
        thread_id: str,
        cwd: str,
        model: str,
        developer_instructions: str,
        config: dict[str, Any] | None,
    ) -> str:
        result = await self._request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": cwd,
                "model": model,
                "sandbox": settings.codex_sandbox_mode,
                "approvalPolicy": settings.codex_approval_policy,
                "developerInstructions": developer_instructions,
                "config": config,
            },
        )
        return result["thread"]["id"]

    async def list_skills(self, *, cwd: str, force_reload: bool = True) -> list[dict[str, Any]]:
        result = await self._request(
            "skills/list",
            {"cwds": [cwd], "forceReload": force_reload},
        )
        rows: list[dict[str, Any]] = []
        for entry in result.get("data", []):
            if entry.get("cwd") != cwd:
                continue
            for skill in entry.get("skills", []):
                if skill.get("enabled"):
                    rows.append(skill)
        return rows

    async def stream_turn(
        self,
        *,
        thread_id: str,
        input_items: list[dict[str, Any]],
        model: str | None = None,
        sandbox_policy: dict[str, Any] | None = None,
    ):
        params: dict[str, Any] = {"threadId": thread_id, "input": input_items}
        if model:
            params["model"] = model
        if sandbox_policy is not None:
            params["sandboxPolicy"] = sandbox_policy

        response, notifications = await self._request(
            "turn/start", params, capture_notifications=True
        )
        turn = response.get("turn", {})
        turn_id = turn.get("id")
        initial_status = turn.get("status")

        completed = False
        for raw in notifications:
            note = self._to_notification(raw)
            if note is None:
                continue
            if note.params.get("turnId") and note.params["turnId"] != turn_id:
                continue
            if note.method == "turn/completed":
                turn = note.params.get("turn", {})
                if turn_id and turn.get("id") != turn_id:
                    continue
                completed = True
            yield note

        if not completed and initial_status in {"completed", "failed", "interrupted"}:
            completed = True
            yield CodexNotification(
                method="turn/completed",
                params={"threadId": thread_id, "turn": turn},
            )

        while not completed:
            raw = await self._next_notification()
            note = self._to_notification(raw)
            if note is None:
                continue
            if note.params.get("turnId") and turn_id and note.params["turnId"] != turn_id:
                continue
            if note.method == "turn/completed":
                turn = note.params.get("turn", {})
                if turn_id and turn.get("id") != turn_id:
                    continue
                completed = True
            yield note

    async def compact_thread(self, *, thread_id: str) -> None:
        await self._request("thread/compact/start", {"threadId": thread_id})

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        capture_notifications: bool = False,
    ) -> Any:
        req_id = self._next_id
        self._next_id += 1
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
        )

        if req_id in self._pending_responses:
            msg = self._pending_responses.pop(req_id)
            result = self._extract_result(msg, method)
            if capture_notifications:
                return result, []
            return result

        buffered: list[dict[str, Any]] = []
        while True:
            msg = await self._read_message()
            if "method" in msg and "id" in msg:
                await self._handle_server_request(msg)
                continue
            if "method" in msg:
                if capture_notifications:
                    buffered.append(msg)
                else:
                    self._queued_notifications.append(msg)
                continue
            if msg.get("id") != req_id:
                self._pending_responses[int(msg["id"])] = msg
                continue
            result = self._extract_result(msg, method)
            if capture_notifications:
                return result, buffered
            if buffered:
                self._queued_notifications.extend(buffered)
            return result

    def _extract_result(self, msg: dict[str, Any], method: str) -> Any:
        if "error" in msg:
            error = msg["error"]
            raise CodexClientError(f"{method} failed: {error}")
        return msg.get("result", {})

    async def _next_notification(self) -> dict[str, Any]:
        if self._queued_notifications:
            return self._queued_notifications.pop(0)
        while True:
            msg = await self._read_message()
            if "method" in msg and "id" in msg:
                await self._handle_server_request(msg)
                continue
            if "method" in msg:
                return msg
            self._pending_responses[int(msg["id"])] = msg

    def _to_notification(self, msg: dict[str, Any]) -> CodexNotification | None:
        method = msg.get("method")
        if not method:
            return None
        params = msg.get("params", {})
        if not isinstance(params, dict):
            params = {}
        return CodexNotification(method=method, params=params)

    async def _handle_server_request(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        request_id = msg.get("id")
        if request_id is None:
            return

        if method in {"execCommandApproval", "item/commandExecution/requestApproval"}:
            payload = {"decision": "decline"}
            await self._send({"jsonrpc": "2.0", "id": request_id, "result": payload})
            return
        if method == "item/fileChange/requestApproval":
            payload = {"decision": "decline"}
            await self._send({"jsonrpc": "2.0", "id": request_id, "result": payload})
            return
        if method == "item/tool/call":
            payload = {
                "success": False,
                "contentItems": [{"type": "inputText", "text": "Dynamic tool calls are not supported."}],
            }
            await self._send({"jsonrpc": "2.0", "id": request_id, "result": payload})
            return
        if method == "item/tool/requestUserInput":
            await self._send({"jsonrpc": "2.0", "id": request_id, "result": {"answers": {}}})
            return

        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unsupported server request: {method}"},
            }
        )

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise CodexClientError("Codex app-server process is not running")
        wire = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        self._process.stdin.write(wire)
        await self._process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if self._process is None or self._process.stdout is None:
            raise CodexClientError("Codex app-server process is not running")
        while True:
            try:
                raw = await asyncio.wait_for(self._process.stdout.readline(), timeout=self._timeout)
            except asyncio.TimeoutError as exc:
                raise CodexClientError("Timed out waiting for codex app-server response") from exc
            except ValueError as exc:
                raise CodexClientError(
                    "Codex app-server emitted a line larger than stream limit "
                    f"({settings.codex_rpc_stream_limit_bytes} bytes). "
                    "Increase CODEX_RPC_STREAM_LIMIT_BYTES."
                ) from exc
            if not raw:
                raise CodexClientError("Codex app-server closed the connection")
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON app-server stdout line: %s", line)
                continue
            if isinstance(msg, dict):
                return msg

    async def _drain_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.debug("codex app-server: %s", text)
