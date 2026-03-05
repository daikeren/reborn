from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture()
def _reset_lock():
    import app.mcp.memory as mem

    mem._write_lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_memory_write_creates_file(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_write

    text = await memory_write("likes black coffee", "preference")
    assert "Saved" in text

    files = list((workspace / "memory").glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "likes black coffee" in content
    assert "[preference]" in content


@pytest.mark.asyncio
async def test_memory_write_appends(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_write

    await memory_write("first entry", "fact")
    await memory_write("second entry", "decision")
    files = list((workspace / "memory").glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "first entry" in content
    assert "second entry" in content


@pytest.mark.asyncio
async def test_memory_write_format(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_write

    with patch("app.mcp.memory.now_tz") as mock_now:
        mock_now.return_value = datetime(2025, 6, 15, 14, 30, tzinfo=ZoneInfo("Asia/Taipei"))
        await memory_write("test format", "fact")

    file = workspace / "memory" / "2025-06-15.md"
    assert file.read_text().strip() == "## 14:30 [fact]\ntest format"


@pytest.mark.asyncio
async def test_memory_search_finds_match(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_search
    from app.utils import today_tz

    mem_dir = workspace / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    today = today_tz()
    (mem_dir / f"{today.isoformat()}.md").write_text("## 10:00 [fact]\nAndy likes black coffee\n")

    result = await memory_search("coffee")
    assert "coffee" in result.lower()
    assert today.isoformat() in result


@pytest.mark.asyncio
async def test_memory_search_core(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_search

    (workspace / "MEMORY.md").write_text("## Preferences\nFavorite color: blue\n")
    result = await memory_search("color")
    assert "Core Memory" in result


@pytest.mark.asyncio
async def test_memory_search_no_results(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_search

    result = await memory_search("nonexistent_xyz")
    assert "No results found" in result


@pytest.mark.asyncio
async def test_memory_update_core_existing_section(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_update_core

    (workspace / "MEMORY.md").write_text("## Preferences\nold\n\n## Projects\nproject info\n")
    await memory_update_core("Preferences", "new content here")
    text = (workspace / "MEMORY.md").read_text()
    assert "new content here" in text
    assert "old" not in text
    assert "project info" in text


@pytest.mark.asyncio
async def test_memory_update_core_new_section(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_update_core

    (workspace / "MEMORY.md").write_text("## Preferences\nexisting\n")
    await memory_update_core("People", "Alice is a friend")
    text = (workspace / "MEMORY.md").read_text()
    assert "## People" in text
    assert "Alice is a friend" in text


@pytest.mark.asyncio
async def test_memory_update_core_atomic(workspace: Path, _reset_lock):
    from app.mcp.memory import memory_update_core

    (workspace / "MEMORY.md").write_text("## Preferences\noriginal\n")
    await memory_update_core("Preferences", "updated")
    leftover = list(workspace.glob(".MEMORY.md.*"))
    assert len(leftover) == 0
    assert "updated" in (workspace / "MEMORY.md").read_text()


def test_memory_server_config_uses_uv_run(workspace: Path):
    from app.mcp.memory import memory_server_config

    cfg = memory_server_config()
    assert cfg["command"] == "uv"
    assert cfg["args"] == ["run", "python", "-m", "app.mcp.server"]
    assert isinstance(cfg["cwd"], str)

