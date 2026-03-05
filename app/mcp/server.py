from __future__ import annotations

from app.mcp.memory import (
    memory_search as _memory_search,
    memory_update_core as _memory_update_core,
    memory_write as _memory_write,
)


def create_server():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("fastmcp is required to run app.mcp.server") from exc

    mcp = FastMCP("reeve-memory")

    @mcp.tool()
    async def memory_write(content: str, category: str) -> str:
        """Append a memory entry to today's daily log."""
        return await _memory_write(content, category)

    @mcp.tool()
    async def memory_search(query: str, days: int = 30) -> str:
        """Search core memory and recent daily logs."""
        return await _memory_search(query, days=days)

    @mcp.tool()
    async def memory_update_core(section: str, content: str) -> str:
        """Update a section in MEMORY.md."""
        return await _memory_update_core(section, content)

    return mcp


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
