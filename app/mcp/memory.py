from __future__ import annotations

import asyncio
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path

from app.config import settings
from app.utils import now_tz, today_tz

_write_lock = asyncio.Lock()


async def memory_write(content: str, category: str) -> str:
    now = now_tz()
    today = now.date()
    time_str = now.strftime("%H:%M")

    mem_dir = settings.workspace_dir / "memory"
    file_path = mem_dir / f"{today.isoformat()}.md"
    entry = f"## {time_str} [{category}]\n{content}\n"

    async with _write_lock:
        mem_dir.mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

    return f"Saved to {today.isoformat()} log."


async def memory_search(query: str, days: int = 30) -> str:
    today = today_tz()
    results: list[str] = []

    core_path = settings.workspace_dir / "MEMORY.md"
    if core_path.exists():
        core_text = core_path.read_text(encoding="utf-8")
        if query.lower() in core_text.lower():
            results.append(f"### Core Memory\n{core_text.strip()}")

    mem_dir = settings.workspace_dir / "memory"
    if mem_dir.exists():
        for i in range(days):
            day = today - timedelta(days=i)
            file_path = mem_dir / f"{day.isoformat()}.md"
            if file_path.exists():
                text = file_path.read_text(encoding="utf-8")
                if query.lower() in text.lower():
                    results.append(f"### {day.isoformat()}\n{text.strip()}")

    if not results:
        return "No results found."

    return "\n\n".join(results)


async def memory_update_core(section: str, content: str) -> str:
    core_path = settings.workspace_dir / "MEMORY.md"

    async with _write_lock:
        if core_path.exists():
            text = core_path.read_text(encoding="utf-8")
        else:
            text = ""

        escaped = re.escape(section)
        pattern = rf"^## {escaped}\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)

        if match:
            text = text[: match.start(1)] + content + "\n" + text[match.end(1) :]
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"\n## {section}\n{content}\n"

        fd, tmp_path = tempfile.mkstemp(
            dir=core_path.parent, prefix=".MEMORY.md.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, core_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    return f"Updated [{section}] in core memory."


def memory_server_config() -> dict:
    """Return MCP stdio config for the local memory server."""
    repo_root = settings.workspace_dir.parent
    return {
        "command": "uv",
        "args": ["run", "python", "-m", "app.mcp.server"],
        "cwd": str(repo_root),
    }
