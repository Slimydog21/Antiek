"""Tests for ``services.html_projection.resolvers.substrate_refs``.

Each test builds a minimal DuckDB with ``init_database_at_path`` and inserts
just enough rows to exercise one resolution path.  The resolver is tested
against a real (tmp) DuckDB — no mocking of the SQL layer.
"""

from __future__ import annotations

import json

import pytest

from substrate.graph.schema import init_database_at_path
from services.html_projection.adapters.notebook import ResolvedRefData
from services.html_projection.resolvers.substrate_refs import resolve_refs


# ── helpers ──────────────────────────────────────────────────────────────

def _db(tmp_path):
    """Create a tmp DuckDB with the full schema and return its path."""
    db_path = str(tmp_path / "test.duckdb")
    init_database_at_path(db_path)
    return db_path


def _insert_node(con, node_id, label, node_type, metadata=None, graph_scope="depth"):
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        [node_id, label, node_type, graph_scope, metadata],
    )


def _insert_document(con, doc_id, title, content_class, ip_holder_id=None):
    con.execute(
        "INSERT INTO documents (document_id, title, content_class, ip_holder_id, "
        "source_tier, document_type) VALUES (?, ?, ?, ?, 1, 'article')",
        [doc_id, title, content_class, ip_holder_id],
    )


def _insert_edge(con, edge_id, source_node_id, target_node_id, relation,
                 source_document_id=None, source_tier=1, graph_scope="depth"):
    con.execute(
        "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
        "source_document_id, source_tier, extraction_confidence, graph_scope) "
        "VALUES (?, ?, ?, ?, ?, ?, 1.0, ?)",
        [edge_id, source_node_id, target_node_id, relation,
         source_document_id, source_tier, graph_scope],
    )


# ── tests ────────────────────────────────────────────────────────────────

class TestResolveRefs:
    """Grouped tests for ``resolve_refs``."""

    def test_claim_with_metadata_source_document(self, tmp_path):
        """A claim whose metadata carries ``source_document_id`` resolves
        with the document's ``content_class`` and the label in ``statement``."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_document(con, "doc-pd", "On Liberty", "public_domain")
            _insert_node(
                con, "c1", "Mill's harm principle", "claim",
                metadata=json.dumps({"source_document_id": "doc-pd"}),
            )

        result = resolve_refs(["c1"], db_path=db)
        assert "c1" in result
        ref = result["c1"]
        assert ref.kind == "claim"
        assert ref.content_class == "public_domain"
        assert ref.ip_holder_id is None
        assert ref.title == "On Liberty"
        assert ref.payload["statement"] == "Mill's harm principle"
        assert ref.payload["text"] == "Mill's harm principle"

    def test_question_with_no_source_document(self, tmp_path):
        """A question with no metadata source and no edge resolves with
        ``content_class=None`` and ``question`` key in the payload."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_node(con, "q1", "What is the capital of France?", "question")

        result = resolve_refs(["q1"], db_path=db)
        assert "q1" in result
        ref = result["q1"]
        assert ref.kind == "question"
        assert ref.content_class is None
        assert ref.ip_holder_id is None
        assert ref.title is None
        assert ref.payload["question"] == "What is the capital of France?"
        assert ref.payload["text"] == "What is the capital of France?"

    def test_claim_with_edge_fallback(self, tmp_path):
        """A claim whose metadata has NO ``source_document_id`` but has a
        ``supported_by`` edge resolves through the edge fallback."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_document(con, "doc-edge", "Edge Doc", "public_domain")
            _insert_node(con, "c2", "Edge-backed claim", "claim")
            # A target node is needed for the edge FK.
            _insert_node(con, "target1", "Target entity", "entity")
            _insert_edge(
                con, "e1", "c2", "target1", "supported_by",
                source_document_id="doc-edge",
            )

        result = resolve_refs(["c2"], db_path=db)
        assert "c2" in result
        ref = result["c2"]
        assert ref.content_class == "public_domain"
        assert ref.title == "Edge Doc"

    def test_personal_reading_reports_rights_faithfully(self, tmp_path):
        """A claim whose source document has ``content_class='personal_reading'``
        resolves with that exact content_class — the resolver does NOT
        pre-filter.  The adapter decides the cite-only treatment."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_document(
                con, "doc-pr", "A PG Essay", "personal_reading",
                ip_holder_id="pg",
            )
            _insert_node(
                con, "c3", "PG's insight", "claim",
                metadata=json.dumps({"source_document_id": "doc-pr"}),
            )

        result = resolve_refs(["c3"], db_path=db)
        ref = result["c3"]
        assert ref.content_class == "personal_reading"
        assert ref.ip_holder_id == "pg"
        assert ref.title == "A PG Essay"
        # The payload text IS present — the adapter, not the resolver, strips it.
        assert ref.payload["statement"] == "PG's insight"

    def test_missing_ref_id_absent_from_result(self, tmp_path):
        """A ref_id with no matching node is omitted, not fabricated."""
        db = _db(tmp_path)
        result = resolve_refs(["nonexistent"], db_path=db)
        assert "nonexistent" not in result
        assert result == {}

    def test_malformed_metadata_json_does_not_raise(self, tmp_path):
        """Malformed JSON in ``nodes.metadata`` is treated as ``{}``; the
        resolver degrades to the edge/None fallback without raising."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_node(
                con, "c4", "Bad metadata claim", "claim",
                metadata="NOT VALID JSON {{{",
            )

        # Should not raise.
        result = resolve_refs(["c4"], db_path=db)
        assert "c4" in result
        ref = result["c4"]
        # No metadata source_document_id, no edge → no document → all None.
        assert ref.content_class is None
        assert ref.title is None

    def test_malformed_metadata_with_edge_fallback(self, tmp_path):
        """Malformed metadata falls back to the edge — and succeeds."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_document(con, "doc-fb", "Fallback Doc", "public_domain")
            _insert_node(
                con, "c5", "Edge fallback claim", "claim",
                metadata="{broken",
            )
            _insert_node(con, "t2", "T2", "entity")
            _insert_edge(
                con, "e2", "c5", "t2", "supported_by",
                source_document_id="doc-fb",
            )

        result = resolve_refs(["c5"], db_path=db)
        ref = result["c5"]
        assert ref.content_class == "public_domain"
        assert ref.title == "Fallback Doc"

    def test_empty_ref_ids_returns_empty(self, tmp_path):
        """An empty input list returns an empty dict without touching the DB."""
        db = _db(tmp_path)
        result = resolve_refs([], db_path=db)
        assert result == {}

    def test_insight_uses_statement_key(self, tmp_path):
        """An insight node gets ``statement`` as its kind-specific payload key."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_node(con, "i1", "Key insight", "insight")

        result = resolve_refs(["i1"], db_path=db)
        ref = result["i1"]
        assert ref.kind == "insight"
        assert ref.payload["statement"] == "Key insight"
        assert ref.payload["text"] == "Key insight"

    def test_entity_uses_body_key(self, tmp_path):
        """An entity node (not claim/insight/question) gets ``body`` as its
        kind-specific payload key."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_node(con, "ent1", "Some entity", "entity")

        result = resolve_refs(["ent1"], db_path=db)
        ref = result["ent1"]
        assert ref.kind == "entity"
        assert ref.payload["body"] == "Some entity"
        assert ref.payload["text"] == "Some entity"

    def test_multiple_refs_mixed_resolution(self, tmp_path):
        """Resolving a batch with one valid, one missing, one with edge
        fallback returns only the two valid ones."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            _insert_document(con, "doc-m", "Mixed Doc", "public_domain")
            _insert_node(
                con, "c-m", "Mixed claim", "claim",
                metadata=json.dumps({"source_document_id": "doc-m"}),
            )
            _insert_node(con, "t-m", "T-m", "entity")
            _insert_node(con, "c-e", "Edge claim", "claim")
            _insert_edge(
                con, "e-m", "c-e", "t-m", "supported_by",
                source_document_id="doc-m",
            )

        result = resolve_refs(["c-m", "missing", "c-e"], db_path=db)
        assert set(result.keys()) == {"c-m", "c-e"}
        assert result["c-m"].content_class == "public_domain"
        assert result["c-e"].content_class == "public_domain"

    def test_node_with_null_metadata_column(self, tmp_path):
        """A node whose ``metadata`` column is SQL NULL (not the string
        'null') resolves without error — treated as ``{}``."""
        db = _db(tmp_path)
        from runtime.db_lock import connect_write

        with connect_write(db, purpose="test") as con:
            # Explicitly insert NULL metadata.
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, "
                "graph_scope, metadata) VALUES (?, ?, ?, ?, NULL)",
                ["c-null", "Null meta claim", "claim", "depth"],
            )

        result = resolve_refs(["c-null"], db_path=db)
        ref = result["c-null"]
        assert ref.content_class is None
        assert ref.payload["statement"] == "Null meta claim"
