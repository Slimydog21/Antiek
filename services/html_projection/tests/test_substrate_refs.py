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
    assert data.payload["statement"] == "Edge-backed claim"


def test_personal_reading_reported_not_prefiltered(graph_db):
    resolved = resolve_refs(["claim-pr"], db_path=graph_db)
    data = resolved["claim-pr"]
    assert data.content_class == "personal_reading"
    assert data.ip_holder_id == "pg"
    assert data.title == "PG Essay"
    assert data.payload["statement"] == "Secret passage"


def test_missing_ref_id_omitted(graph_db):
    resolved = resolve_refs(["does-not-exist"], db_path=graph_db)
    assert resolved == {}


def test_malformed_metadata_falls_back_to_edge(graph_db):
    resolved = resolve_refs(["claim-bad-meta"], db_path=graph_db)
    data = resolved["claim-bad-meta"]
    assert data.content_class == "public_domain"
    assert data.title == "Edge Source"
    assert data.payload["statement"] == "Bad meta claim"