"""Tests for trace-to-source target resolution (specs/write/ SPR-07, backend core).

The mandatory mechanical gate (M4): a block sourced from a GATED book
resolves to servable-snippet, NEVER gated full text — Write must not be a
side door around Read's servability gate. Plus the brainstorm-source and
dangling-source rules.

These unit tests cover target resolution itself. Production command/event and
shared-reader navigation coverage lives in ``test_write_to_read_handoff.py``
and the reading app tests.
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
from substrate.write.outline_block import OutlineBlock, place_block, place_user_authored_block
from substrate.write.trace import resolve_trace_target


def _node_block(node_id: str) -> OutlineBlock:
    return OutlineBlock(
        outline_block_id="probe", section_id="-", block_kind="claim",
        provenance_kind="graph_node", node_id=node_id, source_block_kind=None,
        source_block_id=None, content=None, block_index=0, cluster_id=None,
    )


@pytest.fixture()
def db(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    path = os.path.join(d, "antiek.duckdb")
    init_database_at_path(path)

    def _seed_node(content_class: str | None, *, node_label: str, taken_down=False):
        with connect_write(path, purpose="t") as con:
            doc_id = f"doc-{node_label}"
            insert_document(con, document_id=doc_id, source_tier=2,
                            document_type="book", title=f"Book {node_label}")
            if content_class is not None:
                con.execute("UPDATE documents SET content_class = ? WHERE document_id = ?",
                            [content_class, doc_id])
            if taken_down:
                con.execute(
                    "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
                    [doc_id],
                )
            ch = insert_chunk(con, document_id=doc_id, chunk_index=0, text="passage")
            node = insert_node(con, canonical_label=node_label, node_type="claim",
                               graph_scope="cross_domain", investigation_id="__operator__",
                               metadata={"chunk_id": ch})
        return node, doc_id

    return {"path": path, "seed_node": _seed_node}


def _read(path):
    return duckdb.connect(path, read_only=True)


# ── M4 — the mandatory gated-source-no-leak gate ───────────────────


def test_public_domain_source_opens_at_span(db):
    node, doc = db["seed_node"]("public_domain", node_label="pd")
    con = _read(db["path"])
    target = resolve_trace_target(con, _node_block(node))
    con.close()
    assert target.kind == "source_span"
    assert target.full_text_allowed is True
    assert target.document_id == doc


def test_gated_book_shows_servable_snippet_only(db):
    """A restricted-license book must NEVER trace to full text."""
    node, _ = db["seed_node"]("restricted_pending_opt_in", node_label="gated")
    con = _read(db["path"])
    target = resolve_trace_target(con, _node_block(node))
    con.close()
    assert target.kind == "servable_snippet"
    assert target.full_text_allowed is False  # no leak
    assert "no full text" in target.detail


def test_unknown_content_class_denies_by_default(db):
    """Deny-by-default: NULL/unknown content_class is not servable full text."""
    node, _ = db["seed_node"](None, node_label="unknown")
    con = _read(db["path"])
    target = resolve_trace_target(con, _node_block(node))
    con.close()
    assert target.full_text_allowed is False


def test_taken_down_book_not_servable(db):
    node, _ = db["seed_node"]("public_domain", node_label="td", taken_down=True)
    con = _read(db["path"])
    target = resolve_trace_target(con, _node_block(node))
    con.close()
    assert target.full_text_allowed is False
    assert target.servability_status == "taken_down"


# ── brainstorm + dangling sources ──────────────────────────────────


def test_brainstorm_block_traces_to_session(db):
    with connect_write(db["path"], purpose="t") as con:
        # Need a real section for the user-authored block.
        from substrate.graph.ops import insert_deliverable, insert_section
        did = insert_deliverable(con, title="T", deliverable_kind="general_essay")
        sec = insert_section(con, deliverable_id=did, section_index=0)
        obid = place_user_authored_block(
            con, section_id=sec, content="a brainstorm thought",
            block_kind="user_authored", provenance_kind="brainstorm", block_index=0,
        )
    con = _read(db["path"])
    target = resolve_trace_target(con, obid)
    con.close()
    assert target.kind == "session"
    assert target.document_id is None  # no invented document


def test_dangling_source_is_unavailable(db):
    with connect_write(db["path"], purpose="t") as con:
        from substrate.graph.ops import insert_deliverable, insert_section
        did = insert_deliverable(con, title="T", deliverable_kind="general_essay")
        sec = insert_section(con, deliverable_id=did, section_index=0)
        obid = place_block(
            con, section_id=sec, block_kind="insight", provenance_kind="graph_node",
            node_id="node-gone", block_index=0,
        )
    con = _read(db["path"])
    target = resolve_trace_target(con, obid)
    con.close()
    assert target.kind == "unavailable"
    assert target.full_text_allowed is False
