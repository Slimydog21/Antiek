"""A claim with no source document is an UNSUPPORTED claim, not the operator's
own words (audit wave 3 design record, item 5): it resolves to the gated
default. A question with no source keeps None — the operator asked it."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from services.html_projection.adapters.deliverable import DeliverableBlock
from services.html_projection.resolvers.substrate_refs import resolve_refs
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph.schema import init_database_at_path


@pytest.fixture
def graph_db():
    tmp = tempfile.mkdtemp(prefix="sourceless-")
    db_path = os.path.join(tmp, "graph.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="seed")
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, title, content_class) "
            "VALUES ('doc-pd', 2, 'paper', 'On Liberty', 'public_domain')"
        )
        for node_id, kind, meta in (
            ("claim-orphan", "claim", None),
            ("insight-orphan", "insight", None),
            ("question-orphan", "question", None),
            ("entity-orphan", "entity", None),
            ("claim-sourced", "claim", '{"source_document_id": "doc-pd"}'),
        ):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
                "VALUES (?, ?, ?, 'depth', ?)",
                [node_id, f"{kind} text", kind, meta],
            )
    finally:
        con.close()
    return db_path


def test_sourceless_claim_and_insight_resolve_to_the_gated_default(graph_db):
    out = resolve_refs(["claim-orphan", "insight-orphan"], db_path=graph_db)
    assert out["claim-orphan"].content_class == GATED_DEFAULT_CONTENT_CLASS
    assert out["insight-orphan"].content_class == GATED_DEFAULT_CONTENT_CLASS
    assert out["claim-orphan"].servable is False
    # and a deliverable block built from it withholds (the adapter reads a
    # concrete class, never the None it used to read as "operator prose")
    b = DeliverableBlock(block_kind="claim", text="x", content_class=out["claim-orphan"].content_class)
    assert b.servable is False


def test_control_question_and_entity_without_source_keep_none(graph_db):
    out = resolve_refs(["question-orphan", "entity-orphan"], db_path=graph_db)
    assert out["question-orphan"].content_class is None
    assert out["entity-orphan"].content_class is None


def test_control_sourced_claim_carries_its_document_class(graph_db):
    out = resolve_refs(["claim-sourced"], db_path=graph_db)
    assert out["claim-sourced"].content_class == "public_domain"
    assert out["claim-sourced"].servable is True
