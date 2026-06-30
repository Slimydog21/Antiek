"""Typed errors for the Antiek MCP server."""

from __future__ import annotations


class NoteNotFoundError(Exception):
    """Raised when a private note cannot be located by user_id + note_id."""

    def __init__(self, user_id: str, note_id: str) -> None:
        self.user_id = user_id
        self.note_id = note_id
        super().__init__(f"Note not found: user_id={user_id}, note_id={note_id}")
