"""End-to-end integration tests for the Antiek MCP server (MCP-SPR-04).

Full MCP lifecycle: start server → list resources → read resource →
call tool → verify output. Hermetic (DuckDB temp file, no network).

Covers all 3 resources (private note, user notes list, public note)
+ 4 tools (search_personal, search_public, cite_source, record_attribution).
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path


@pytest.fixture()
def db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_mcp_e2e.duckdb")


@pytest.fixture()
def _init_db(db_path: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    init_database_at_path(db_path)
    return db_path


def _seed_full_dataset(db_path: str) -> None:
    """Seed a complete dataset covering all resources and tools."""
    con = duckdb.connect(db_path)

    # Private notes for user-42
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
                "priv-note-1",
                "My Research Notes",
                "Alice",
                "Quantum computing leverages qubits in superposition "
                "for exponential speedup on certain problems.",
                json.dumps({"tags": ["research", "quantum"]}),
                3,
                "note",
                "user-42",
                "personal_reading",
                None,
            ),
            (
                "priv-note-2",
                "Meeting Minutes",
                "Alice",
                "Discussion about machine learning pipeline improvements "
                "and neural network architecture choices.",
                None,
                3,
                "note",
                "user-42",
                "user_owned",
                None,
            ),
        ],
    )

    # Public notes
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
                "pub-note-1",
                "Quantum Error Correction",
                "Dr. Smith",
                "Surface codes are the leading approach to quantum "
                "error correction for fault-tolerant computation.",
                json.dumps({"license": "cc-by"}),
                1,
                "article",
                "researcher-1",
                "source_declared_open",
                "ipholder-nature",
            ),
            (
                "pub-note-2",
                "Deep Reinforcement Learning",
                "Prof. Lee",
                "Deep reinforcement learning combines neural networks "
                "with reward-based learning. AlphaGo demonstrated this.",
                None,
                2,
                "article",
                "researcher-2",
                "user_public_contribution",
                None,
            ),
            (
                "gated-note-1",
                "Restricted Content",
                "Publisher",
                "This should never appear in public search.",
                None,
                1,
                "article",
                "publisher-1",
                "restricted_pending_opt_in",
                "ipholder-elsevier",
            ),
        ],
    )

    # Chunks for cite_source
    con.execute(
        """
        INSERT INTO chunks (
            chunk_id, document_id, chunk_index, section_path, text, token_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "chunk-quantum-1",
            "pub-note-1",
            0,
            "Section 1 > Error Correction",
            "Surface codes are the leading approach.",
            8,
        ],
    )

    con.close()


@pytest.fixture()
def _seed(_init_db: str) -> str:
    _seed_full_dataset(_init_db)
    return _init_db


# ---------------------------------------------------------------------------
# Resources: full lifecycle
# ---------------------------------------------------------------------------


class TestE2EResources:
    """Full lifecycle: list templates → read each resource type."""

    async def test_list_resource_templates(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        templates = await mcp.list_resource_templates()
        uris = {t.uriTemplate for t in templates}
        assert "antiek://private/notes/{user_id}/{note_id}" in uris
        assert "antiek://private/notes/{user_id}" in uris
        assert "antiek://public/notes/{note_id}" in uris

    async def test_read_private_note(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource(
            "antiek://private/notes/user-42/priv-note-1"
        )
        assert len(result) == 1
        note = json.loads(result[0].content)
        assert note["document_id"] == "priv-note-1"
        assert note["title"] == "My Research Notes"
        assert "qubits" in note["content"]
        assert note["owner_user_id"] == "user-42"
        assert note["metadata"]["tags"] == ["research", "quantum"]

    async def test_read_user_notes_list(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://private/notes/user-42")
        notes = json.loads(result[0].content)
        assert len(notes) == 2
        ids = {n["document_id"] for n in notes}
        assert ids == {"priv-note-1", "priv-note-2"}
        for n in notes:
            assert "content" not in n

    async def test_read_public_note_with_attribution(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://public/notes/pub-note-1")
        note = json.loads(result[0].content)
        assert note["document_id"] == "pub-note-1"
        assert note["ip_holder_id"] == "ipholder-nature"
        assert note["content_class"] == "source_declared_open"
        # Content should be wrapped (M1 defense)
        assert note["content"].startswith('<antiek:content trusted="false">')
        assert "Surface codes" in note["content"]

    async def test_read_gated_public_note_raises(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Licensing required"):
            await mcp.read_resource("antiek://public/notes/gated-note-1")

    async def test_read_missing_private_note_raises(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="Note not found"):
            await mcp.read_resource(
                "antiek://private/notes/user-42/nonexistent"
            )

    async def test_read_missing_public_note_raises(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        with pytest.raises(ValueError, match="not found"):
            await mcp.read_resource("antiek://public/notes/nonexistent")


# ---------------------------------------------------------------------------
# Tools: full lifecycle
# ---------------------------------------------------------------------------


class TestE2ETools:
    """Full lifecycle: list tools → call each tool → verify output."""

    async def test_list_tools(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "search_personal" in names
        assert "search_public" in names
        assert "cite_source" in names
        assert "record_attribution" in names

    def test_search_personal_returns_ranked_results(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed)
        try:
            result = search_personal(
                con, "quantum computing", user_id="user-42", top_k=5,
            )
        finally:
            con.close()

        assert result["query"] == "quantum computing"
        assert result["top_k"] == 5
        assert len(result["results"]) >= 1
        top = result["results"][0]
        assert top["note_id"] == "priv-note-1"
        assert top["score"] > 0
        assert "snippet" in top
        assert "title" in top

    def test_search_personal_scoped_to_user(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed)
        try:
            result = search_personal(con, "quantum", user_id="user-42")
        finally:
            con.close()

        note_ids = [r["note_id"] for r in result["results"]]
        # Should not include public notes or other users' notes
        assert all(nid.startswith("priv-") for nid in note_ids)

    def test_search_public_with_attribution_and_gating(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.defenses import is_content_wrapped
        from services.mcp_server.tools import search_public

        con = connect_read(_seed)
        try:
            result = search_public(con, "quantum error correction")
        finally:
            con.close()

        assert len(result["results"]) >= 1
        doc_ids = [r["document_id"] for r in result["results"]]
        assert "pub-note-1" in doc_ids
        # Gated content excluded
        assert "gated-note-1" not in doc_ids

        # Attribution metadata present
        pub1 = next(r for r in result["results"] if r["document_id"] == "pub-note-1")
        assert pub1["ip_holder_id"] == "ipholder-nature"
        assert pub1["content_class"] == "source_declared_open"

        # Snippets are wrapped (M1 defense)
        for r in result["results"]:
            assert is_content_wrapped(r["snippet"])

    def test_search_public_excludes_gated_content(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed)
        try:
            result = search_public(con, "restricted content publisher")
        finally:
            con.close()

        doc_ids = [r["document_id"] for r in result["results"]]
        assert "gated-note-1" not in doc_ids

    def test_cite_source_chunk_resolution(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed)
        try:
            citation = cite_source(con, "chunk-quantum-1", id_type="chunk")
        finally:
            con.close()

        assert citation["chunk_id"] == "chunk-quantum-1"
        assert citation["document_id"] == "pub-note-1"
        assert citation["title"] == "Quantum Error Correction"
        assert citation["author"] == "Dr. Smith"
        assert citation["source_tier"] == 1
        assert citation["ip_holder_id"] == "ipholder-nature"
        assert citation["section_path"] == "Section 1 > Error Correction"
        assert "Dr. Smith" in citation["formatted_citation"]
        assert "Quantum Error Correction" in citation["formatted_citation"]

    def test_cite_source_document_resolution(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed)
        try:
            citation = cite_source(con, "pub-note-1", id_type="document")
        finally:
            con.close()

        assert citation["chunk_id"] is None
        assert citation["document_id"] == "pub-note-1"
        assert citation["title"] == "Quantum Error Correction"

    def test_cite_source_missing_raises(self, _seed: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import SourceNotFoundError
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed)
        try:
            with pytest.raises(SourceNotFoundError):
                cite_source(con, "nonexistent-chunk")
        finally:
            con.close()

    def test_record_attribution_event_lifecycle(
        self,
        _seed: str,
        tmp_path: Any,
    ) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import record_attribution
        from substrate.event_log import trajectory

        events_dir = str(tmp_path / "events")
        con = connect_read(_seed)
        try:
            result = record_attribution(
                con,
                "chunk-quantum-1",
                consumer_id="agent-e2e",
                timestamp="2026-06-30T11:00:00Z",
                investigation_id="inv-mcp-e2e",
                session_dwell_seconds=7.0,
                events_dir=events_dir,
            )
        finally:
            con.close()

        assert result["event_id"] is not None
        assert result["document_id"] == "pub-note-1"
        rows = trajectory("inv-mcp-e2e", events_dir=events_dir)
        assert len(rows) == 1
        assert rows[0]["action_type"] == "mcp.attribution.recorded"
        assert rows[0]["payload"]["consumer_id"] == "agent-e2e"
        assert rows[0]["payload"]["source_id"] == "chunk-quantum-1"
        assert rows[0]["document_id"] == "pub-note-1"


# ---------------------------------------------------------------------------
# Defense integration
# ---------------------------------------------------------------------------


class TestE2EDefenses:
    """Verify defenses are integrated end-to-end."""

    async def test_public_note_content_wrapped_in_resource(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource("antiek://public/notes/pub-note-1")
        note = json.loads(result[0].content)
        assert note["content"].startswith('<antiek:content trusted="false">')

    async def test_private_note_content_not_wrapped(self, _seed: str) -> None:
        from services.mcp_server.server import mcp

        result = await mcp.read_resource(
            "antiek://private/notes/user-42/priv-note-1"
        )
        note = json.loads(result[0].content)
        assert "<antiek:content" not in note["content"]

    async def test_manifest_matches_live_tools(self, _seed: str) -> None:
        from services.mcp_server.manifest import generate_manifest, verify_manifest
        from services.mcp_server.server import mcp

        tools = await mcp.list_tools()
        tool_dicts = [
            {"name": t.name, "description": t.description}
            for t in tools
        ]
        manifest = generate_manifest(tool_dicts)
        assert verify_manifest(tool_dicts, manifest) == []
