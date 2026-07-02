"""SPR-06: notebook export wiring — resolve_notebook_export resolves REAL refs.

Proves the full path on real substrate fixture rows (a notebook -> a claim_card
block -> a claim node -> a source document with a content_class): NOT mocked.
This is what validates that the resolved_refs wiring works end-to-end, the gap
the earlier degraded resolved_refs={} left open.
"""

from __future__ import annotations

import json

from interfaces.research.api import notebook_artifact as mod


def _seed(db_path: str) -> None:
    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    con = connect_write(db_path)
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "content_class, ip_holder_id, title) VALUES (?, ?, ?, ?, ?, ?)",
            ["doc1", 1, "article", "public_domain", None, "On Liberty"],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                "c1",
                "REAL CLAIM TEXT",
                "claim",
                "depth",
                json.dumps({"source_document_id": "doc1"}),
            ],
        )
        con.execute(
            "INSERT INTO notebooks (notebook_id, title) VALUES (?, ?)",
            ["nb1", "My notebook"],
        )
        con.execute(
            "INSERT INTO notebook_blocks (block_id, notebook_id, block_index, "
            "block_type, ref_id, content_json) VALUES (?, ?, ?, ?, ?, ?)",
            [
                "b1",
                "nb1",
                0,
                "claim_card",
                "c1",
                json.dumps({"type": "antiek_claim_card", "attrs": {"claim_id": "c1"}}),
            ],
        )
    finally:
        con.close()


def test_notebook_export_resolves_real_refs(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    _seed(db)
    source = mod.resolve_notebook_export("nb1", db_path=db)
    assert source is not None
    assert "c1" in source.resolved_refs
    rr = source.resolved_refs["c1"]
    assert rr.content_class == "public_domain"
    assert "REAL CLAIM TEXT" in json.dumps(rr.payload)

    # End-to-end: the export adapter inlines the resolved claim text.
    from services.html_projection.adapters.notebook_export import adapt_notebook_for_export
    from services.html_projection.context import RenderContext
    from services.html_projection.renderer import render

    dm = adapt_notebook_for_export(
        source.content_tiptap, title=source.title, resolved_refs=source.resolved_refs
    )
    assert "REAL CLAIM TEXT" in render(dm, RenderContext())


def test_notebook_export_missing_returns_none(tmp_path):
    from substrate.graph import ensure_initialized

    db = str(tmp_path / "g.duckdb")
    ensure_initialized(db)
    assert mod.resolve_notebook_export("nope", db_path=db) is None
