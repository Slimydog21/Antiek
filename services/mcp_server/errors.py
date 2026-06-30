"""Typed errors for the Antiek MCP server."""

from __future__ import annotations


class NoteNotFoundError(Exception):
    """Raised when a private note cannot be located by user_id + note_id."""

    def __init__(self, user_id: str, note_id: str) -> None:
        self.user_id = user_id
        self.note_id = note_id
        super().__init__(f"Note not found: user_id={user_id}, note_id={note_id}")


class PublicNoteNotFoundError(Exception):
    """Raised when a public note cannot be located by note_id."""

    def __init__(self, note_id: str) -> None:
        self.note_id = note_id
        super().__init__(f"Public note not found: note_id={note_id}")


class EmptyQueryError(Exception):
    """Raised when a search tool receives an empty or whitespace query."""

    def __init__(self, tool_name: str = "search") -> None:
        self.tool_name = tool_name
        super().__init__(f"{tool_name} requires a non-empty query")


class SourceNotFoundError(Exception):
    """Raised when a citation source cannot be resolved."""

    def __init__(self, source_id: str, id_type: str) -> None:
        self.source_id = source_id
        self.id_type = id_type
        super().__init__(f"Source not found: id={source_id}, id_type={id_type}")


class LicensingRequiredError(Exception):
    """Raised when a public note's content is gated (§9.0).

    The note exists but its content_class requires publisher opt-in
    before it can be served on a non-privileged path.
    """

    def __init__(self, note_id: str, content_class: str) -> None:
        self.note_id = note_id
        self.content_class = content_class
        super().__init__(
            f"Licensing required for note {note_id} "
            f"(content_class={content_class}). "
            f"Publisher opt-in needed per §9.0."
        )


class BookChunkNotFoundError(Exception):
    """Raised when a book chunk cannot be located by ISBN + chunk_id."""

    def __init__(self, isbn: str, chunk_id: str) -> None:
        self.isbn = isbn
        self.chunk_id = chunk_id
        super().__init__(f"Book chunk not found: isbn={isbn}, chunk_id={chunk_id}")
