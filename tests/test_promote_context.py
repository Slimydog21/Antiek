"""Tests for pre-outline context-window promotion (specs/write/ SPR-08 M4).

A loose context window (placed blocks + objective) promotes to a
structured Deliverable/Section/OutlineBlock, preserving every block's
provenance — node-backed stays node-backed, user-originated stays
user-originated (no fabricated citation).

The context-window surface, objective-by-voice intake, and the generation
call (reused from SPR-06) are the UI/runtime layer; the promotion +
provenance-preservation core is what's unit-tested here.
"""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document, insert_node
from substrate.graph.schema import init_database_at_path
from substrate.write.outline_block import list_section_blocks
from substrate.write.promote_context import ContextBlockSpec, promote_to_outline
from substrate.write.provenance import resolve_provenance


@pytest.fixture()
def db(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    path = os.path.join(d, "antiek.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="test/seed") as con:
        doc = insert_document(con, document_id="doc-1", source_tier=2,
                              document_type="paper", title="Source")
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="a sourced insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
    return {"path": path, "node": node, "document": doc}


def _read(path):
    return duckdb.connect(path, read_only=True)


def test_promote_creates_deliverable_with_blocks(db):
    specs = [
        ContextBlockSpec(block_kind="insight", provenance_kind="graph_node", node_id=db["node"]),
        ContextBlockSpec(block_kind="user_authored", provenance_kind="brainstorm",
                         content="a thought I had aloud"),
    ]
    with connect_write(db["path"], purpose="t") as con:
        result = promote_to_outline(
            con, title="From a context window", deliverable_kind="general_essay",
            specs=specs, owner_user_id="user-context",
            objective="argue that the edit is the writing",
        )
    assert len(result.block_ids) == 2
    con = _read(db["path"])
    # Deliverable + section exist; objective recorded on the section title.
    sec = con.execute(
        "SELECT title FROM deliverable_sections WHERE section_id = ?",
        [result.section_id],
    ).fetchone()
    assert "edit is the writing" in (sec[0] or "")
    blocks = list_section_blocks(con, result.section_id)
    con.close()
    assert len(blocks) == 2


def test_promotion_preserves_provenance(db):
    specs = [
        ContextBlockSpec(block_kind="insight", provenance_kind="graph_node", node_id=db["node"]),
        ContextBlockSpec(block_kind="user_authored", provenance_kind="brainstorm",
                         content="user-originated"),
    ]
    with connect_write(db["path"], purpose="t") as con:
        result = promote_to_outline(
            con, title="T", deliverable_kind="general_essay", specs=specs,
            owner_user_id="user-context",
        )
    con = _read(db["path"])
    blocks = {b.block_kind: b for b in list_section_blocks(con, result.section_id)}
    # The node-backed block still resolves to its source document.
    node_chain = resolve_provenance(con, blocks["insight"])
    user_chain = resolve_provenance(con, blocks["user_authored"])
    con.close()
    assert node_chain.status == "resolved"
    assert node_chain.document_id == db["document"]
    # The user-originated block carries no fabricated source.
    assert user_chain.status == "user_originated"
    assert blocks["user_authored"].node_id is None
