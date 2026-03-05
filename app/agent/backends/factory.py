from __future__ import annotations

from app.agent.backends.base import RuntimeBackend
from app.agent.backends.claude_backend import ClaudeBackend
from app.agent.backends.codex_backend import CodexBackend
from app.agent.types import AgentError
from app.config import settings


def get_runtime_backend() -> RuntimeBackend:
    backend = settings.agent_backend.strip().lower()
    if backend == "codex":
        return CodexBackend()
    if backend == "claude":
        return ClaudeBackend()
    raise AgentError(
        f"Unsupported AGENT_BACKEND={settings.agent_backend!r}; expected 'codex' or 'claude'"
    )

