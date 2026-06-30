"""MCP resource definitions for the Antiek server.

Registers the ``antiek://private/notes/{user_id}/{note_id}`` resource
template backed by the DuckDB ``documents`` table.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .errors import NoteNotFoundError
from .reader import _resolve_db_path, get_note, list_user_notes


def register_resources(mcp: FastMCP) -> None:
    """Register all Antiek MCP resources on the given FastMCP server."""

    @mcp.resource(
        "antiek://private/notes/{user_id}/{note_id}",
        name="private_note",
        title="Private Note",
        description="A private note owned by the specified user, read-only.",
        mime_type="application/json",
    )
    def private_note(user_id: str, note_id: str) -> str:
        """Fetch a single private note as JSON."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            note = get_note(con, user_id, note_id)
        except NoteNotFoundError:
            raise
        finally:
            con.close()
        return json.dumps(note, default=str)

    @mcp.resource(
        "antiek://private/notes/{user_id}",
        name="user_notes",
        title="User Notes",
        description="List all private notes owned by a user.",
        mime_type="application/json",
    )
    def user_notes(user_id: str) -> str:
        """List all notes for a user as JSON."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            notes = list_user_notes(con, user_id)
        finally:
            con.close()
        return json.dumps(notes, default=str)
