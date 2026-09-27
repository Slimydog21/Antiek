"""Tests for services.html_projection.resolvers.substrate_refs."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from services.html_projection.resolvers.substrate_refs import resolve_refs
from substrate.graph.schema import init_database_at_path


@pytest.fixture
def graph_db():
    tmp = tempfile.mkdtemp(prefix="substrate-refs-")
    db_path = os.path.join(tmp, "graph.duckdb")
    init_database_at_path(db_path)

    con = connect_write(db_path, purpose="substrate_refs_seed")
    try:
        for doc_id, title, content_class, ip_holder in (
            ("doc-pd", "On Liberty", "public_domain", None),
            ("doc-edge", "Edge Source", "public_domain", "holder-edge"),
            ("doc-pr", "PG Essay", "personal_reading", "pg"),
        ):
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_tier, document_type, title, content_class, ip_holder_id) "
                "VALUES (?, 2, 'paper', ?, ?, ?)",
                [doc_id, title, content_class, ip_holder],
            )

        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, ?, ?, 'depth', ?)",
            [
                "claim-meta",
                "Liberty claim text",
                "claim",
                json.dumps({"source_document_id": "doc-pd"}),
            ],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('question-orphan', 'What is liberty?', 'question', 'depth', NULL)"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('claim-edge', 'Edge-backed claim', 'claim', 'depth', NULL)"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('node-target', 'target', 'entity', 'depth')"
        )
        con.execute(
            "INSERT INTO edges "
            "(edge_id, source_node_id, target_node_id, relation, source_document_id, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-supported', 'claim-edge', 'node-target', 'supported_by', "
            "'doc-edge', 2, 0.9, 'depth')"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, ?, ?, 'depth', ?)",
            [
                "claim-pr",
                "Secret passage",
                "claim",
                json.dumps({"source_document_id": "doc-pr"}),
            ],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('claim-bad-meta', 'Bad meta claim', 'claim', 'depth', '{not-json')"
        )
        con.execute(
            "INSERT INTO edges "
            "(edge_id, source_node_id, target_node_id, relation, source_document_id, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-bad-meta', 'claim-bad-meta', 'node-target', 'supported_by', "
            "'doc-edge', 2, 0.9, 'depth')"
        )
    finally:
        con.close()

    yield db_path


def test_claim_from_metadata_public_domain(graph_db):
    resolved = resolve_refs(["claim-meta"], db_path=graph_db)
    assert set(resolved) == {"claim-meta"}
    data = resolved["claim-meta"]
    assert data.kind == "claim"
    assert data.content_class == "public_domain"
    assert data.title == "On Liberty"
    assert data.source_document_id == "doc-pd"
    assert data.payload["statement"] == "Liberty claim text"
    assert data.payload["text"] == "Liberty claim text"


def test_question_without_source_has_none_rights(graph_db):
    resolved = resolve_refs(["question-orphan"], db_path=graph_db)
    data = resolved["question-orphan"]
    assert data.content_class is None
    assert data.ip_holder_id is None
    assert data.title is None
    assert data.payload["question"] == "What is liberty?"


def test_claim_resolves_source_via_supported_by_edge(graph_db):
    resolved = resolve_refs(["claim-edge"], db_path=graph_db)
    data = resolved["claim-edge"]
    assert data.content_class == "public_domain"
    assert data.title == "Edge Source"
    assert data.ip_holder_id == "holder-edge"
    assert data.source_document_id == "doc-edge"
    assert data.payload["statement"] == "Edge-backed claim"


def test_personal_reading_reported_not_prefiltered(graph_db):
    resolved = resolve_refs(["claim-pr"], db_path=graph_db)
    data = resolved["claim-pr"]
    assert data.content_class == "personal_reading"
    assert data.ip_holder_id == "pg"
    assert data.title == "PG Essay"
    assert data.source_document_id == "doc-pr"
    assert data.payload["statement"] == "Secret passage"


def test_missing_ref_id_omitted(graph_db):
    resolved = resolve_refs(["does-not-exist"], db_path=graph_db)
    assert resolved == {}


def test_malformed_metadata_is_an_unresolved_pointer_not_an_empty_one(graph_db):
    # Metadata that cannot be parsed may name any source (a truncated
    # '{"source_chunk_ids": ["c-restricted"]' hides one), so it binds the node
    # to the gated default even though its supported_by edge is public. The
    # node still resolves, with its text, for the cite-only notice.
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

    resolved = resolve_refs(["claim-bad-meta"], db_path=graph_db)
    data = resolved["claim-bad-meta"]
    assert data.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert data.servable is False
    assert data.payload["statement"] == "Bad meta claim"


def _add_claim(db_path: str, node_id: str, metadata: dict) -> None:
    con = connect_write(db_path, purpose="substrate_refs_seed")
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, 'Mixed claim', 'claim', 'depth', ?)",
            [node_id, json.dumps(metadata)],
        )
    finally:
        con.close()


def test_restricted_supported_by_edge_binds_over_public_metadata(graph_db):
    # Every grounding pointer is read: a public metadata source does not hide
    # a supported_by edge onto a personal-reading essay.
    _add_claim(graph_db, "claim-mixed", {"source_document_id": "doc-pd"})
    con = connect_write(graph_db, purpose="substrate_refs_seed")
    try:
        con.execute(
            "INSERT INTO edges "
            "(edge_id, source_node_id, target_node_id, relation, source_document_id, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-mixed', 'claim-mixed', 'node-target', 'supported_by', "
            "'doc-pr', 2, 0.9, 'depth')"
        )
    finally:
        con.close()
    data = resolve_refs(["claim-mixed"], db_path=graph_db)["claim-mixed"]
    assert data.content_class == "personal_reading"
    assert data.source_document_id == "doc-pr"
    assert data.servable is False


def test_missing_metadata_chunk_resolves_to_the_gated_default(graph_db):
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

    _add_claim(
        graph_db, "claim-chunk-gone",
        {"source_document_id": "doc-pd", "chunk_id": "chunk-gone"},
    )
    data = resolve_refs(["claim-chunk-gone"], db_path=graph_db)["claim-chunk-gone"]
    assert data.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert data.servable is False



def test_source_chunk_ids_entry_that_is_gone_resolves_to_the_gated_default(graph_db):
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

    _add_claim(
        graph_db, "claim-src-chunks-gone",
        {"source_document_id": "doc-pd", "source_chunk_ids": ["chunk-gone"]},
    )
    data = resolve_refs(["claim-src-chunks-gone"], db_path=graph_db)["claim-src-chunks-gone"]
    assert data.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert data.servable is False


def test_an_unnamed_pointer_field_binds_the_node_rights(graph_db):
    # alt_doc_id is named by no code; its shape alone makes it a pointer.
    _add_claim(
        graph_db, "claim-alt-doc",
        {"source_document_id": "doc-pd", "notes": {"alt_doc_id": "doc-pr"}},
    )
    data = resolve_refs(["claim-alt-doc"], db_path=graph_db)["claim-alt-doc"]
    assert data.content_class == "personal_reading"
    assert data.source_document_id == "doc-pr"
    assert data.servable is False


def test_pointer_free_metadata_keys_are_not_sources(graph_db):
    # source_event_ids names events, not substrate rows: not a pointer key.
    _add_claim(
        graph_db, "claim-events-only",
        {"source_document_id": "doc-pd", "source_event_ids": ["evt-1"],
         "origin_note_id": "note-1"},
    )
    data = resolve_refs(["claim-events-only"], db_path=graph_db)["claim-events-only"]
    assert data.content_class == "public_domain"
    assert data.source_document_id == "doc-pd"
