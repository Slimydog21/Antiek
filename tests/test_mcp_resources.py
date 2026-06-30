"""Tests for MCP resources (MCP-SPR-02 + MCP-SPR-03).

Covers:
- Public notes resource (antiek://public/notes/{note_id})
- Read-only with attribution metadata
- Gated notes return licensing-required error (§9.0)
- Resource template registration
- Book chunk resource (antiek://books/{isbn}/{chunk_id})
- Public-domain books return content
- Gated books return licensing error
- Missing books return typed error
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path


@pytest.fixture()
def db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_mcp_resources.duckdb")


@pytest.fixture()
def _init_db(db_path: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Initialize the graph schema and set the env var."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    init_database_at_path(db_path)
    return db_path


def _insert_doc(
    con: duckdb.DuckDBPyConnection,
    *,
    doc_id: str,
    title: str,
    raw_text: str,
    owner_user_id: str = "user-1",
    source_tier: int = 3,
    document_type: str = "note",
    content_class: str | None = None,
    ip_holder_id: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO documents (
            document_id, title, author, raw_text, metadata,
            source_tier, document_type, owner_user_id,
            content_class, ip_holder_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            doc_id, title, "Test Author", raw_text,
            json.dumps({"tags": ["test"]}),
            source_tier, document_type, owner_user_id,
            content_class, ip_holder_id,
        ],
    )


@pytest.fixture()
def _seed_public_notes(_init_db: str) -> str:
    """Seed public notes of various content classes."""
    con = duckdb.connect(_init_db)
    _insert_doc(
        con,
        doc_id="pub-1",
        title="Public Note",
        raw_text="This is a public note about quantum physics.",
        content_class=None,
    )
    _insert_doc(
        con,
        doc_id="pub-2",
        title="User Contribution",
        raw_text="Deep learning analysis of protein structures.",
        content_class="user_public_contribution",
    )
    _insert_doc(
        con,
        doc_id="pub-3",
        title="Licensed Publisher Content",
        raw_text="Analysis of market trends in renewable energy.",
        content_class="opt_in_licensed",
        ip_holder_id="ipholder-cambridge",
    )
    _insert_doc(
        con,
        doc_id="gated-1",
        title="Restricted Content",
        raw_text="This content is pending publisher opt-in.",
        content_class="restricted_pending_opt_in",
        ip_holder_id="ipholder-nature",
    )
    _insert_doc(
        con,
        doc_id="gated-2",
        title="Personal Reading",
        raw_text="My private reading notes on this article.",
        content_class="personal_reading",
    )
    con.close()
    return _init_db


# ---------------------------------------------------------------------------
# M3: Public notes resource
# ---------------------------------------------------------------------------


class TestGetPublicNote:
    """get_public_note returns content with attribution metadata."""

    def test_returns_content_and_attribution(self, _seed_public_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            note = get_public_note(con, "pub-1")
        finally:
            con.close()

        assert note["document_id"] == "pub-1"
        assert note["title"] == "Public Note"
        assert "quantum physics" in note["content"]
        assert "ip_holder_id" in note
        assert "content_class" in note

    def test_opt_in_licensed_has_ip_holder(self, _seed_public_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            note = get_public_note(con, "pub-3")
        finally:
            con.close()

        assert note["ip_holder_id"] == "ipholder-cambridge"
        assert note["content_class"] == "opt_in_licensed"

    def test_user_public_contribution_accessible(self, _seed_public_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            note = get_public_note(con, "pub-2")
        finally:
            con.close()

        assert note["content_class"] == "user_public_contribution"

    def test_missing_note_raises(self, _seed_public_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import PublicNoteNotFoundError
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            with pytest.raises(PublicNoteNotFoundError) as exc_info:
                get_public_note(con, "nonexistent")
            assert exc_info.value.note_id == "nonexistent"
        finally:
            con.close()


class TestGatedNoteLicensing:
    """Gated notes raise LicensingRequiredError (§9.0)."""

    def test_restricted_pending_opt_in_raises(
        self, _seed_public_notes: str,
    ) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import LicensingRequiredError
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            with pytest.raises(LicensingRequiredError) as exc_info:
                get_public_note(con, "gated-1")
            assert exc_info.value.note_id == "gated-1"
            assert exc_info.value.content_class == "restricted_pending_opt_in"
            assert "§9.0" in str(exc_info.value)
        finally:
            con.close()

    def test_personal_reading_raises(self, _seed_public_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import LicensingRequiredError
        from services.mcp_server.reader import get_public_note

        con = connect_read(_seed_public_notes)
        try:
            with pytest.raises(LicensingRequiredError) as exc_info:
                get_public_note(con, "gated-2")
            assert exc_info.value.content_class == "personal_reading"
        finally:
            con.close()


class TestPublicResourceTemplate:
    """The public notes resource template is registered on the server."""

    async def test_public_note_template_registered(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        uris = [t.uriTemplate for t in templates]
        assert "antiek://public/notes/{note_id}" in uris

    async def test_public_note_template_metadata(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        by_uri = {t.uriTemplate: t for t in templates}
        tmpl = by_uri["antiek://public/notes/{note_id}"]
        assert tmpl.name == "public_note"
        assert tmpl.mimeType == "application/json"

    async def test_read_public_note_via_server(
        self, _seed_public_notes: str,
    ) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://public/notes/pub-1")
        assert len(result) == 1
        content = json.loads(result[0].content)
        assert content["document_id"] == "pub-1"
        assert "content_class" in content

    async def test_read_gated_note_via_server_raises(
        self, _seed_public_notes: str,
    ) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Licensing required"):
            await mcp.read_resource("antiek://public/notes/gated-1")

    async def test_read_missing_public_note_via_server_raises(
        self, _seed_public_notes: str,
    ) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="not found"):
            await mcp.read_resource("antiek://public/notes/nonexistent")


# ---------------------------------------------------------------------------
# M3 (MCP-SPR-03): Book chunk resource
# ---------------------------------------------------------------------------


def _insert_book(
    con: duckdb.DuckDBPyConnection,
    *,
    doc_id: str,
    title: str,
    isbn: str,
    raw_text: str,
    content_class: str | None = None,
    ip_holder_id: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO documents (
            document_id, title, author, raw_text, metadata,
            source_tier, document_type, content_class, ip_holder_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            doc_id, title, "Test Author", raw_text,
            json.dumps({"isbn": isbn, "tags": ["book"]}),
            3, "book", content_class, ip_holder_id,
        ],
    )


def _insert_chunk(
    con: duckdb.DuckDBPyConnection,
    *,
    chunk_id: str,
    document_id: str,
    chunk_index: int,
    text: str,
    section_path: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO chunks (chunk_id, document_id, chunk_index, section_path, text, token_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [chunk_id, document_id, chunk_index, section_path, text, len(text.split())],
    )


@pytest.fixture()
def _seed_books(_init_db: str) -> str:
    """Seed books of various content classes with chunks."""
    con = duckdb.connect(_init_db)
    _insert_book(
        con,
        doc_id="book-pd",
        title="Public Domain Classic",
        isbn="9780141439518",
        raw_text="It is a truth universally acknowledged...",
        content_class="public_domain",
    )
    _insert_chunk(
        con,
        chunk_id="chunk-pd-1",
        document_id="book-pd",
        chunk_index=0,
        text="It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
        section_path="Chapter 1",
    )
    _insert_book(
        con,
        doc_id="book-gated",
        title="Gated Publisher Book",
        isbn="9780262033848",
        raw_text="This is gated content...",
        content_class="restricted_pending_opt_in",
        ip_holder_id="ipholder-mit",
    )
    _insert_chunk(
        con,
        chunk_id="chunk-gated-1",
        document_id="book-gated",
        chunk_index=0,
        text="Chapter 1 of a restricted book.",
        section_path="Chapter 1",
    )
    _insert_book(
        con,
        doc_id="book-personal",
        title="Personal Reading",
        isbn="9780061120084",
        raw_text="My private reading...",
        content_class="personal_reading",
    )
    _insert_chunk(
        con,
        chunk_id="chunk-personal-1",
        document_id="book-personal",
        chunk_index=0,
        text="Personal reading notes.",
        section_path="Notes",
    )
    con.close()
    return _init_db


class TestGetBookChunk:
    """get_book_chunk returns content with §9.0 gating."""

    def test_public_domain_returns_content(self, _seed_books: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_book_chunk

        con = connect_read(_seed_books)
        try:
            chunk = get_book_chunk(con, "9780141439518", "chunk-pd-1")
        finally:
            con.close()

        assert chunk["chunk_id"] == "chunk-pd-1"
        assert chunk["document_id"] == "book-pd"
        assert chunk["isbn"] == "9780141439518"
        assert "truth universally acknowledged" in chunk["text"]
        assert chunk["content_class"] == "public_domain"
        assert chunk["title"] == "Public Domain Classic"

    def test_gated_book_raises_licensing_error(self, _seed_books: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import LicensingRequiredError
        from services.mcp_server.reader import get_book_chunk

        con = connect_read(_seed_books)
        try:
            with pytest.raises(LicensingRequiredError) as exc_info:
                get_book_chunk(con, "9780262033848", "chunk-gated-1")
            assert exc_info.value.content_class == "restricted_pending_opt_in"
            assert "§9.0" in str(exc_info.value)
        finally:
            con.close()

    def test_personal_reading_raises_licensing_error(self, _seed_books: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import LicensingRequiredError
        from services.mcp_server.reader import get_book_chunk

        con = connect_read(_seed_books)
        try:
            with pytest.raises(LicensingRequiredError) as exc_info:
                get_book_chunk(con, "9780061120084", "chunk-personal-1")
            assert exc_info.value.content_class == "personal_reading"
        finally:
            con.close()

    def test_missing_isbn_raises(self, _seed_books: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import BookChunkNotFoundError
        from services.mcp_server.reader import get_book_chunk

        con = connect_read(_seed_books)
        try:
            with pytest.raises(BookChunkNotFoundError) as exc_info:
                get_book_chunk(con, "9999999999999", "chunk-1")
            assert exc_info.value.isbn == "9999999999999"
        finally:
            con.close()

    def test_missing_chunk_raises(self, _seed_books: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import BookChunkNotFoundError
        from services.mcp_server.reader import get_book_chunk

        con = connect_read(_seed_books)
        try:
            with pytest.raises(BookChunkNotFoundError) as exc_info:
                get_book_chunk(con, "9780141439518", "nonexistent-chunk")
            assert exc_info.value.chunk_id == "nonexistent-chunk"
        finally:
            con.close()


class TestBookResourceTemplate:
    """The book chunk resource template is registered on the server."""

    async def test_book_chunk_template_registered(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        uris = [t.uriTemplate for t in templates]
        assert "antiek://books/{isbn}/{chunk_id}" in uris

    async def test_book_chunk_template_metadata(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        by_uri = {t.uriTemplate: t for t in templates}
        tmpl = by_uri["antiek://books/{isbn}/{chunk_id}"]
        assert tmpl.name == "book_chunk"
        assert tmpl.mimeType == "application/json"

    async def test_read_book_chunk_via_server(
        self, _seed_books: str,
    ) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://books/9780141439518/chunk-pd-1")
        assert len(result) == 1
        content = json.loads(result[0].content)
        assert content["chunk_id"] == "chunk-pd-1"
        assert content["isbn"] == "9780141439518"
        assert "content_class" in content

    async def test_read_gated_book_via_server_raises(
        self, _seed_books: str,
    ) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Licensing required"):
            await mcp.read_resource("antiek://books/9780262033848/chunk-gated-1")

    async def test_read_missing_book_via_server_raises(
        self, _seed_books: str,
    ) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="not found"):
            await mcp.read_resource("antiek://books/9999999999999/chunk-1")
