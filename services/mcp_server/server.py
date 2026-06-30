"""FastMCP server for Antiek — serves substrate resources over stdio.

This module creates the ``FastMCP`` app and registers resource handlers.
The server is read-only: every DuckDB connection goes through
``runtime.db_lock.connect_read`` (no write lock, no flock).

Single-writer invariant (§16): when deploying behind uvicorn, use
``--workers 1``. The MCP server itself writes nothing, but the host
process must not introduce a second writer.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .resources import register_resources

mcp = FastMCP(
    name="antiek",
    instructions=(
        "Antiek research substrate — read-only access to private notes "
        "and documents via the DuckDB knowledge graph."
    ),
)

register_resources(mcp)


def main() -> None:
    """Entry point: run the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
