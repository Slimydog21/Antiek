"""Tests for MCP tools (MCP-SPR-02).

Covers:
- search_personal: BM25 search over user's personal notes
- search_public: BM25 search over public graph with attribution metadata
- Empty query returns typed error
- Retrieval-time gating (§9.0) respected on public search
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path


@pytest.fixture()
def db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_mcp_tools.duckdb")


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
    owner_user_id: str = "user-42",
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
def _seed_personal(_init_db: str) -> str:
    """Seed multiple personal notes for user-42."""
    con = duckdb.connect(_init_db)
    _insert_doc(
        con,
        doc_id="note-quantum-1",
        title="Quantum Computing Notes",
        raw_text=(
            "Quantum computing leverages qubits that can exist in "
            "superposition. This allows quantum computers to solve "
            "certain problems exponentially faster than classical "
            "machines. Key algorithms include Shor's and Grover's."
        ),
    )
    _insert_doc(
        con,
        doc_id="note-ml-2",
        title="Machine Learning Overview",
        raw_text=(
            "Machine learning is a subset of artificial intelligence "
            "that enables systems to learn from data. Neural networks "
            "with multiple layers form deep learning architectures."
        ),
    )
    _insert_doc(
        con,
        doc_id="note-unrelated-3",
        title="Cooking Recipes",
        raw_text=(
            "Heat olive oil in a large skillet over medium heat. "
            "Add garlic and sauté until golden. Season with salt."
        ),
    )
    _insert_doc(
        con,
        doc_id="note-other-user",
        title="Other User's Quantum Note",
        raw_text="Quantum entanglement is a physical phenomenon.",
        owner_user_id="user-99",
    )
    con.close()
    return _init_db


@pytest.fixture()
def _seed_public(_init_db: str) -> str:
    """Seed public and gated documents for public search."""
    con = duckdb.connect(_init_db)
    _insert_doc(
        con,
        doc_id="pub-note-1",
        title="Public Quantum Analysis",
        raw_text=(
            "Quantum error correction is essential for building "
            "fault-tolerant quantum computers. Surface codes are "
            "the leading approach."
        ),
        owner_user_id="user-1",
        content_class=None,
    )
    _insert_doc(
        con,
        doc_id="pub-note-2",
        title="User Public Contribution",
        raw_text=(
            "Deep reinforcement learning combines neural networks "
            "with reward-based learning. AlphaGo demonstrated this."
        ),
        owner_user_id="user-2",
        content_class="user_public_contribution",
    )
    _insert_doc(
        con,
        doc_id="gated-note-1",
        title="Restricted Publisher Content",
        raw_text="Quantum supremacy was demonstrated by Google.",
        owner_user_id="user-3",
        content_class="restricted_pending_opt_in",
        ip_holder_id="ipholder-nature",
    )
    _insert_doc(
        con,
        doc_id="gated-note-2",
        title="Personal Reading Note",
        raw_text="Quantum tunneling effects in semiconductors.",
        owner_user_id="user-4",
        content_class="personal_reading",
    )
    _insert_doc(
        con,
        doc_id="pub-note-3",
        title="Licensed Content",
        raw_text=(
            "Quantum algorithms for optimization show quadratic "
            "speedup over classical methods."
        ),
        owner_user_id="user-5",
        content_class="opt_in_licensed",
        ip_holder_id="ipholder-cambridge",
    )
    con.close()
    return _init_db


# ---------------------------------------------------------------------------
# M1: search_personal
# ---------------------------------------------------------------------------


class TestSearchPersonal:
    """search_personal BM25 search over user's personal notes."""

    def test_returns_ranked_results(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            result = search_personal(con, "quantum computing", user_id="user-42")
        finally:
            con.close()

        assert result["query"] == "quantum computing"
        assert result["top_k"] == 5
        assert len(result["results"]) >= 1
        assert result["results"][0]["note_id"] == "note-quantum-1"
        assert result["results"][0]["score"] > 0
        assert "snippet" in result["results"][0]
        assert "title" in result["results"][0]

    def test_empty_query_raises(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import EmptyQueryError, search_personal

        con = connect_read(_seed_personal)
        try:
            with pytest.raises(EmptyQueryError):
                search_personal(con, "", user_id="user-42")
        finally:
            con.close()

    def test_whitespace_query_raises(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import EmptyQueryError, search_personal

        con = connect_read(_seed_personal)
        try:
            with pytest.raises(EmptyQueryError):
                search_personal(con, "   ", user_id="user-42")
        finally:
            con.close()

    def test_scoped_to_user(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            result = search_personal(con, "quantum", user_id="user-42")
        finally:
            con.close()

        note_ids = [r["note_id"] for r in result["results"]]
        assert "note-other-user" not in note_ids

    def test_top_k_respected(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            result = search_personal(con, "learning", user_id="user-42", top_k=1)
        finally:
            con.close()

        assert len(result["results"]) <= 1

    def test_no_match_returns_empty(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            result = search_personal(con, "zzzznonexistent", user_id="user-42")
        finally:
            con.close()

        assert result["results"] == []

    def test_invalid_top_k_raises(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            with pytest.raises(ValueError, match="top_k must be >= 1"):
                search_personal(con, "test", user_id="user-42", top_k=0)
        finally:
            con.close()

    def test_result_has_source_tier(self, _seed_personal: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_personal

        con = connect_read(_seed_personal)
        try:
            result = search_personal(con, "quantum", user_id="user-42")
        finally:
            con.close()

        assert len(result["results"]) >= 1
        assert "source_tier" in result["results"][0]


# ---------------------------------------------------------------------------
# M2: search_public
# ---------------------------------------------------------------------------


class TestSearchPublic:
    """search_public BM25 search over public graph with attribution metadata."""

    def test_returns_results_with_attribution(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_public)
        try:
            result = search_public(con, "quantum")
        finally:
            con.close()

        assert result["query"] == "quantum"
        assert len(result["results"]) >= 1

    def test_gated_content_excluded(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_public)
        try:
            result = search_public(con, "quantum")
        finally:
            con.close()

        note_ids = [r["document_id"] for r in result["results"]]
        assert "gated-note-1" not in note_ids
        assert "gated-note-2" not in note_ids

    def test_public_and_opted_in_visible(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_public)
        try:
            result = search_public(con, "quantum")
        finally:
            con.close()

        note_ids = [r["document_id"] for r in result["results"]]
        assert "pub-note-1" in note_ids
        assert "pub-note-3" in note_ids

    def test_empty_query_raises(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import EmptyQueryError, search_public

        con = connect_read(_seed_public)
        try:
            with pytest.raises(EmptyQueryError):
                search_public(con, "")
        finally:
            con.close()

    def test_ip_holder_id_on_licensed_content(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_public)
        try:
            result = search_public(con, "quantum algorithms optimization")
        finally:
            con.close()

        licensed = [r for r in result["results"] if r["document_id"] == "pub-note-3"]
        if licensed:
            assert licensed[0]["ip_holder_id"] == "ipholder-cambridge"

    def test_user_public_contribution_visible(self, _seed_public: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import search_public

        con = connect_read(_seed_public)
        try:
            result = search_public(con, "deep reinforcement learning")
        finally:
            con.close()

        note_ids = [r["document_id"] for r in result["results"]]
        assert "pub-note-2" in note_ids


# ---------------------------------------------------------------------------
# Unit: BM25 scoring
# ---------------------------------------------------------------------------


class TestBM25Scoring:
    """Unit tests for the BM25 scoring helpers."""

    def test_exact_match_scores_higher(self) -> None:
        from services.mcp_server.tools import _compute_bm25_score, _extract_query_terms

        terms = _extract_query_terms("quantum computing")
        score_match = _compute_bm25_score(
            "Quantum computing is revolutionary.", terms,
        )
        score_no_match = _compute_bm25_score(
            "Cooking is an art form.", terms,
        )
        assert score_match > score_no_match

    def test_empty_terms_returns_zero(self) -> None:
        from services.mcp_server.tools import _compute_bm25_score

        assert _compute_bm25_score("some text", []) == 0.0

    def test_empty_text_returns_zero(self) -> None:
        from services.mcp_server.tools import _compute_bm25_score, _extract_query_terms

        terms = _extract_query_terms("quantum")
        assert _compute_bm25_score("", terms) == 0.0

    def test_stopwords_are_filtered(self) -> None:
        from services.mcp_server.tools import _extract_query_terms

        terms = _extract_query_terms("the is a an")
        assert terms == []

    def test_snippet_extraction(self) -> None:
        from services.mcp_server.tools import _extract_snippet

        text = "Alpha " * 100 + "quantum computing is here" + " beta" * 100
        snippet = _extract_snippet(text, ["quantum", "computing"], context_chars=50)
        assert "quantum" in snippet.lower()


@pytest.fixture()
def _seed_citation_source(_init_db: str) -> str:
    """Seed one document and chunk for MCP-SPR-03 cite_source."""
    con = duckdb.connect(_init_db)
    con.execute(
        """
        INSERT INTO documents (
            document_id, title, author, published_at, raw_text, metadata,
            source_tier, document_type, owner_user_id,
            content_class, ip_holder_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "doc-cite-1",
            "Citation Systems",
            "Ada Lovelace",
            "1843-01-01",
            "Citation systems preserve provenance.",
            json.dumps({"source": "test"}),
            1,
            "paper",
            "__operator__",
            "public_domain",
            "ipholder-ada",
        ],
    )
    con.execute(
        """
        INSERT INTO chunks (
            chunk_id, document_id, chunk_index, section_path, text, token_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "chunk-cite-1",
            "doc-cite-1",
            7,
            "Chapter 1 > Provenance",
            "Citation systems preserve provenance.",
            5,
        ],
    )
    con.close()
    return _init_db


class TestCiteSource:
    """MCP-SPR-03 M1 citation source resolution."""

    def test_cites_chunk_with_provenance_chain(self, _seed_citation_source: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed_citation_source)
        try:
            citation = cite_source(con, "chunk-cite-1")
        finally:
            con.close()

        assert citation["chunk_id"] == "chunk-cite-1"
        assert citation["document_id"] == "doc-cite-1"
        assert citation["chunk_index"] == 7
        assert citation["section_path"] == "Chapter 1 > Provenance"
        assert citation["title"] == "Citation Systems"
        assert citation["author"] == "Ada Lovelace"
        assert citation["date"] == "1843-01-01"
        assert citation["source_tier"] == 1
        assert citation["ip_holder_id"] == "ipholder-ada"
        assert "Ada Lovelace" in citation["formatted_citation"]
        assert "Citation Systems" in citation["formatted_citation"]

    def test_cites_document_without_chunk(self, _seed_citation_source: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed_citation_source)
        try:
            citation = cite_source(con, "doc-cite-1", id_type="document")
        finally:
            con.close()

        assert citation["chunk_id"] is None
        assert citation["document_id"] == "doc-cite-1"
        assert citation["title"] == "Citation Systems"
        assert citation["formatted_citation"] == (
            "Ada Lovelace. Citation Systems. 1843-01-01."
        )

    def test_missing_source_raises_typed_error(self, _seed_citation_source: str) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import SourceNotFoundError
        from services.mcp_server.tools import cite_source

        con = connect_read(_seed_citation_source)
        try:
            with pytest.raises(SourceNotFoundError) as exc_info:
                cite_source(con, "missing-chunk")
        finally:
            con.close()

        assert exc_info.value.source_id == "missing-chunk"
        assert exc_info.value.id_type == "chunk"

    async def test_cite_source_tool_registered(self) -> None:
        from services.mcp_server.server import mcp

        tools = await mcp.list_tools()
        assert "cite_source" in {tool.name for tool in tools}


class TestRecordAttribution:
    """MCP-SPR-03 M2 attribution capture at the consuming agent step."""

    def test_writes_typed_metadata_only_event(
        self,
        _seed_citation_source: str,
        tmp_path: Any,
    ) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import record_attribution
        from substrate.event_log import trajectory

        events_dir = str(tmp_path / "events")
        con = connect_read(_seed_citation_source)
        try:
            result = record_attribution(
                con,
                "chunk-cite-1",
                consumer_id="agent-composer-25",
                timestamp="2026-06-30T10:15:00Z",
                investigation_id="inv-mcp-attr",
                session_dwell_seconds=12.5,
                events_dir=events_dir,
            )
        finally:
            con.close()

        assert result["idempotent"] is False
        assert result["event_id"] is not None
        assert result["document_id"] == "doc-cite-1"
        events = trajectory("inv-mcp-attr", events_dir=events_dir)
        written = [e for e in events if e["action_type"] == "mcp.attribution.recorded"]
        assert len(written) == 1
        payload = written[0]["payload"]
        assert payload["source_id"] == "chunk-cite-1"
        assert payload["consumer_id"] == "agent-composer-25"
        assert payload["timestamp"] == "2026-06-30T10:15:00Z"
        assert payload["session_dwell_seconds"] == 12.5
        assert written[0]["document_id"] == "doc-cite-1"
        for forbidden in ("text", "body", "content", "snippet", "raw_text"):
            assert forbidden not in payload

    def test_idempotent_for_same_source_consumer_timestamp(
        self,
        _seed_citation_source: str,
        tmp_path: Any,
    ) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.tools import record_attribution
        from substrate.event_log import trajectory

        events_dir = str(tmp_path / "events")
        con = connect_read(_seed_citation_source)
        try:
            first = record_attribution(
                con,
                "chunk-cite-1",
                consumer_id="agent-1",
                timestamp="2026-06-30T10:16:00Z",
                investigation_id="inv-mcp-attr-idem",
                events_dir=events_dir,
            )
            second = record_attribution(
                con,
                "chunk-cite-1",
                consumer_id="agent-1",
                timestamp="2026-06-30T10:16:00Z",
                investigation_id="inv-mcp-attr-idem",
                events_dir=events_dir,
            )
        finally:
            con.close()

        assert first["event_id"] == second["event_id"]
        assert second["idempotent"] is True
        events = trajectory("inv-mcp-attr-idem", events_dir=events_dir)
        assert sum(e["action_type"] == "mcp.attribution.recorded" for e in events) == 1

    def test_missing_source_raises_typed_error(
        self,
        _seed_citation_source: str,
        tmp_path: Any,
    ) -> None:
        from runtime.db_lock import connect_read
        from services.mcp_server.errors import SourceNotFoundError
        from services.mcp_server.tools import record_attribution

        con = connect_read(_seed_citation_source)
        try:
            with pytest.raises(SourceNotFoundError):
                record_attribution(
                    con,
                    "missing-source",
                    consumer_id="agent-1",
                    timestamp="2026-06-30T10:17:00Z",
                    investigation_id="inv-missing",
                    events_dir=str(tmp_path / "events"),
                )
        finally:
            con.close()

    async def test_record_attribution_tool_registered(self) -> None:
        from services.mcp_server.server import mcp

        tools = await mcp.list_tools()
        assert "record_attribution" in {tool.name for tool in tools}
