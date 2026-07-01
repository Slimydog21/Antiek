"""MCP resource definitions for the Antiek server.

Registers:
- ``antiek://private/notes/{user_id}/{note_id}`` — private note (existing)
- ``antiek://private/notes/{user_id}`` — user notes list (existing)
- ``antiek://public/notes/{note_id}`` — public note with attribution metadata (M3)
- ``antiek://books/{isbn}/{chunk_id}`` — book chunk with §9.0 gating (MCP-SPR-03)
"""

from __future__ import annotations

import json

from .defenses import wrap_untrusted_content
from .errors import NoteNotFoundError
from .fastmcp_compat import FastMCP
from .reader import (
    _resolve_db_path,
    get_account_scope,
    get_book_chunk,
    get_note,
    get_public_note,
    list_account_events,
    list_user_notes,
)


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

    @mcp.resource(
        "antiek://account/events/{user_id}",
        name="account_events",
        title="Account Events",
        description=(
            "Typed account lifecycle and graph-scope events for one user. "
            "Read-only Sprint 19 plumbing; does not activate multi-user auth."
        ),
        mime_type="application/json",
    )
    def account_events(user_id: str) -> str:
        """List typed user.registered / identity / scope events as JSON."""
        return json.dumps(list_account_events(user_id), default=str)

    @mcp.resource(
        "antiek://account/scope/{user_id}",
        name="account_scope",
        title="Account Scope",
        description=(
            "Reconstructed account registration and current graph-routing "
            "scope from typed events."
        ),
        mime_type="application/json",
    )
    def account_scope(user_id: str) -> str:
        """Fetch the reconstructed account/scope summary as JSON."""
        return json.dumps(get_account_scope(user_id), default=str)

    @mcp.resource(
        "antiek://public/notes/{note_id}",
        name="public_note",
        title="Public Note",
        description=(
            "A public note with attribution metadata. "
            "Gated notes return a licensing-required error."
        ),
        mime_type="application/json",
    )
    def public_note(note_id: str) -> str:
        """Fetch a public note with attribution metadata as JSON."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            note = get_public_note(con, note_id)
        finally:
            con.close()
        note["content"] = wrap_untrusted_content(note["content"])
        return json.dumps(note, default=str)

    @mcp.resource(
        "antiek://books/{isbn}/{chunk_id}",
        name="book_chunk",
        title="Book Chunk",
        description=(
            "A book chunk by ISBN and chunk ID. "
            "Public-domain books return content; "
            "gated books return a licensing-required error per §9.0."
        ),
        mime_type="application/json",
    )
    def book_chunk(isbn: str, chunk_id: str) -> str:
        """Fetch a book chunk with §9.0 retrieval-time gating as JSON."""
        from runtime.db_lock import connect_read

        db_path = _resolve_db_path()
        con = connect_read(db_path)
        try:
            chunk = get_book_chunk(con, isbn, chunk_id)
        finally:
            con.close()
        return json.dumps(chunk, default=str)
