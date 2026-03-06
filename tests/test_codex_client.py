from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent.codex_client import CodexAppServerClient, CodexClientError


@dataclass(frozen=True)
class _FakeSettings:
    codex_app_server_command: tuple[str, ...] = ("codex", "app-server")
    codex_rpc_timeout_seconds: float = 60.0
    codex_rpc_stream_limit_bytes: int = 123456
    codex_sandbox_mode: str = "workspace-write"
    codex_approval_policy: str = "never"


class _FakeStdin:
    def write(self, _wire: bytes) -> None:
        return

    async def drain(self) -> None:
        return


class _FakeReadable:
    def __init__(self, line: bytes = b""):
        self._line = line

    async def readline(self) -> bytes:
        return self._line


class _FailingStdout:
    async def readline(self) -> bytes:
        raise ValueError("Separator is found, but chunk is longer than limit")


class _FakeProcess:
    def __init__(self, *, stdout: Any, stderr: Any):
        self.stdin = _FakeStdin()
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0

    def terminate(self) -> None:
        return

    def kill(self) -> None:
        return

    async def wait(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_aenter_passes_stream_limit_to_create_subprocess_exec(monkeypatch):
    import app.config

    old = app.config._settings
    app.config._settings = _FakeSettings(codex_rpc_stream_limit_bytes=654321)
    try:
        captured: dict[str, Any] = {}

        async def _fake_create_subprocess_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return _FakeProcess(stdout=_FakeReadable(b""), stderr=_FakeReadable(b""))

        monkeypatch.setattr(
            "asyncio.create_subprocess_exec", _fake_create_subprocess_exec
        )
        monkeypatch.setattr(
            CodexAppServerClient, "initialize", AsyncMock(return_value=None)
        )

        async with CodexAppServerClient():
            pass

        assert captured["cmd"] == ("codex", "app-server")
        assert captured["kwargs"]["limit"] == 654321
    finally:
        app.config._settings = old


@pytest.mark.asyncio
async def test_read_message_wraps_line_too_long_error():
    import app.config

    old = app.config._settings
    app.config._settings = _FakeSettings(codex_rpc_stream_limit_bytes=777777)
    try:
        client = CodexAppServerClient()
        client._process = _FakeProcess(
            stdout=_FailingStdout(), stderr=_FakeReadable(b"")
        )

        with pytest.raises(CodexClientError) as exc:
            await client._read_message()

        message = str(exc.value)
        assert "larger than stream limit" in message
        assert "777777" in message
        assert "CODEX_RPC_STREAM_LIMIT_BYTES" in message
    finally:
        app.config._settings = old
