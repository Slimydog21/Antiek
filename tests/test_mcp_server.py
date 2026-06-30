"""Tests for the Antiek MCP server.

Covers:
- Existing note returns content + metadata
- Missing note returns NoteNotFoundError
- Server starts without error (FastMCP app construction)
- list_resources returns typed resources
- search_personal/search_public return ranked results
- public notes include attribution metadata and enforce retrieval-time gating
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path


@pytest.fixture()
def db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_mcp.duckdb")


@pytest.fixture()
def _init_db(db_path: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Initialize the graph schema and set the env var."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    init_database_at_path(db_path)
    return db_path


@pytest.fixture()
def _seed_note(_init_db: str) -> str:
    """Insert a test document into the DB and return its document_id."""
    con = duckdb.connect(_init_db)
    con.execute(
        """
        INSERT INTO documents (
            document_id, title, author, raw_text, metadata,
            source_tier, document_type, owner_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "note-abc-123",
            "My Private Note",
            "Test Author",
            "This is the note content.",
            json.dumps({"tags": ["test", "mcp"]}),
            3,
            "note",
            "user-42",
        ],
    )
    con.close()
    return _init_db


@pytest.fixture()
def _seed_search_notes(_init_db: str) -> str:
    """Insert personal, public, and gated documents for MCP-SPR-02."""
    con = duckdb.connect(_init_db)
    con.executemany(
        """
        INSERT INTO documents (
            document_id, title, author, raw_text, metadata,
            source_tier, document_type, owner_user_id,
            content_class, ip_holder_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "personal-alpha",
                "Private Alpha",
                "User",
                "alpha alpha private memory about design systems",
                json.dumps({"tags": ["personal"]}),
                3,
                "note",
                "user-42",
                "personal_reading",
                None,
            ),
            (
                "personal-beta",
                "Private Beta",
                "User",
                "beta private memory",
                None,
                3,
                "note",
                "user-42",
                "user_owned",
                None,
            ),
            (
                "public-alpha",
                "Public Alpha",
                "Publisher",
                "alpha public graph source for attribution routing",
                json.dumps({"license": "open"}),
                1,
                "article",
                "publisher-user",
                "source_declared_open",
                "ip-holder-1",
            ),
            (
                "gated-alpha",
                "Gated Alpha",
                "Publisher",
                "alpha gated source must not leak",
                None,
                1,
                "article",
                "publisher-user",
                "restricted_pending_opt_in",
                "ip-holder-2",
            ),
        ],
    )
    con.close()
    return _init_db


class TestNoteNotFound:
    """NoteNotFoundError is raised for missing notes."""

    def test_missing_note_raises(self, _init_db: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import NoteNotFoundError
        from services.mcp_server.reader import get_note

        con = connect_read(_init_db)
        try:
            with pytest.raises(NoteNotFoundError) as exc_info:
                get_note(con, "user-42", "nonexistent-id")
            assert exc_info.value.user_id == "user-42"
            assert exc_info.value.note_id == "nonexistent-id"
        finally:
            con.close()

    def test_wrong_user_raises(self, _seed_note: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import NoteNotFoundError
        from services.mcp_server.reader import get_note

        con = connect_read(_seed_note)
        try:
            with pytest.raises(NoteNotFoundError):
                get_note(con, "wrong-user", "note-abc-123")
        finally:
            con.close()


class TestGetNote:
    """Existing note returns content + metadata."""

    def test_returns_content_and_metadata(self, _seed_note: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_note

        con = connect_read(_seed_note)
        try:
            result = get_note(con, "user-42", "note-abc-123")
        finally:
            con.close()

        assert result["document_id"] == "note-abc-123"
        assert result["title"] == "My Private Note"
        assert result["author"] == "Test Author"
        assert result["content"] == "This is the note content."
        assert result["source_tier"] == 3
        assert result["document_type"] == "note"
        assert result["owner_user_id"] == "user-42"
        assert result["metadata"]["tags"] == ["test", "mcp"]

    def test_missing_metadata_handled(self, _init_db: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_note

        con = duckdb.connect(_init_db)
        con.execute(
            """
            INSERT INTO documents (
                document_id, title, author, raw_text, source_tier,
                document_type, owner_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ["note-no-meta", "No Meta Note", "Author", "Body", 1, "note", "u1"],
        )
        con.close()

        con = connect_read(_init_db)
        try:
            result = get_note(con, "u1", "note-no-meta")
            assert result["metadata"] == {}
        finally:
            con.close()

    def test_invalid_json_metadata_falls_back(self, _init_db: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import get_note

        con = duckdb.connect(_init_db)
        con.execute(
            """
            INSERT INTO documents (
                document_id, title, author, raw_text, metadata,
                source_tier, document_type, owner_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["note-bad-json", "Bad JSON", "A", "B", "not-json{", 1, "note", "u1"],
        )
        con.close()

        con = connect_read(_init_db)
        try:
            result = get_note(con, "u1", "note-bad-json")
            assert result["metadata"]["_raw"] == "not-json{"
        finally:
            con.close()


class TestListUserNotes:
    """list_user_notes returns summary rows."""

    def test_lists_notes_for_user(self, _seed_note: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import list_user_notes

        con = connect_read(_seed_note)
        try:
            notes = list_user_notes(con, "user-42")
        finally:
            con.close()

        assert len(notes) == 1
        assert notes[0]["document_id"] == "note-abc-123"
        assert notes[0]["title"] == "My Private Note"
        # raw_text should not be in list results
        assert "content" not in notes[0]

    def test_empty_list_for_unknown_user(self, _seed_note: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.reader import list_user_notes

        con = connect_read(_seed_note)
        try:
            notes = list_user_notes(con, "no-such-user")
        finally:
            con.close()

        assert notes == []


class TestServerStartup:
    """Server constructs without error and exposes expected resources."""

    def test_mcp_app_constructs(self) -> None:
        from services.mcp_server.server import mcp

        assert mcp.name == "antiek"

    async def test_list_resource_templates(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        uris = [t.uriTemplate for t in templates]
        assert "antiek://private/notes/{user_id}/{note_id}" in uris
        assert "antiek://private/notes/{user_id}" in uris
        assert "antiek://public/notes/{note_id}" in uris

    async def test_resource_template_names(self) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        by_name = {t.name: t for t in templates}
        assert "private_note" in by_name
        assert "user_notes" in by_name
        assert "public_note" in by_name
        assert by_name["private_note"].mimeType == "application/json"
        assert by_name["user_notes"].mimeType == "application/json"
        assert by_name["public_note"].mimeType == "application/json"

    async def test_list_tools(self) -> None:
        from services.mcp_server.server import mcp

        tools = await mcp.list_tools()
        by_name = {t.name: t for t in tools}
        assert "search_personal" in by_name
        assert "search_public" in by_name


class TestResourceRead:
    """Integration: reading a resource through the FastMCP server."""

    async def test_read_existing_note(self, _seed_note: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource(
            "antiek://private/notes/user-42/note-abc-123"
        )
        assert len(result) == 1
        content = json.loads(result[0].content)
        assert content["document_id"] == "note-abc-123"
        assert content["title"] == "My Private Note"

    async def test_read_missing_note_raises(self, _seed_note: str) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Note not found"):
            await mcp.read_resource(
                "antiek://private/notes/user-42/nonexistent"
            )

    async def test_read_public_note_with_attribution(self, _seed_search_notes: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://public/notes/public-alpha")
        assert len(result) == 1
        content = json.loads(result[0].content)
        assert content["document_id"] == "public-alpha"
        assert content["content_class"] == "source_declared_open"
        assert content["ip_holder_id"] == "ip-holder-1"
        assert content["metadata"]["license"] == "open"

    async def test_read_gated_public_note_raises(self, _seed_search_notes: str) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Licensing required"):
            await mcp.read_resource("antiek://public/notes/gated-alpha")


class TestSearchTools:
    """MCP-SPR-02 search function coverage."""

    def test_search_personal_ranks_user_notes(self, _seed_search_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_search_notes)
        try:
            result = search_personal(con, "alpha design", user_id="user-42", top_k=2)
        finally:
            con.close()

        assert result["query"] == "alpha design"
        assert result["top_k"] == 2
        assert [r["note_id"] for r in result["results"]] == ["personal-alpha"]
        assert result["results"][0]["score"] > 0
        assert "alpha" in result["results"][0]["snippet"]

    def test_search_personal_empty_query_typed_error(self, _seed_search_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import EmptyQueryError
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_search_notes)
        try:
            with pytest.raises(EmptyQueryError) as exc_info:
                search_personal(con, "  ", user_id="user-42")
        finally:
            con.close()
        assert exc_info.value.tool_name == "search_personal"

    def test_search_public_excludes_gated_notes(self, _seed_search_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_search_notes)
        try:
            result = search_public(con, "alpha source", top_k=5)
        finally:
            con.close()

        note_ids = [r["note_id"] for r in result["results"]]
        assert "public-alpha" in note_ids
        assert "gated-alpha" not in note_ids
        public = next(r for r in result["results"] if r["note_id"] == "public-alpha")
        assert public["ip_holder_id"] == "ip-holder-1"
        assert public["content_class"] == "source_declared_open"

    def test_search_public_empty_query_typed_error(self, _seed_search_notes: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import EmptyQueryError
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_search_notes)
        try:
            with pytest.raises(EmptyQueryError) as exc_info:
                search_public(con, "\t")
        finally:
            con.close()
        assert exc_info.value.tool_name == "search_public"
