"""SPR-06: deliverable export wiring — section_blocks resolve REAL refs + rights.

Proves on real substrate fixture rows that a deliverable's section_blocks ref
(a claim node citing a personal_reading document) resolves to its text + the
source's content_class, and that adapt_deliverable cite-only's it (no leak).
"""

from __future__ import annotations

import json

from interfaces.research.api import deliverable_artifact as mod


def _seed(db_path: str) -> None:
    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    con = connect_write(db_path)
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "content_class, ip_holder_id, title) VALUES (?, ?, ?, ?, ?, ?)",
            ["docP", 1, "book", "personal_reading", "pg", "A PG essay"],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            ["cl1", "SECRET DELIVERABLE TEXT", "claim", "depth", json.dumps({"source_document_id": "docP"})],
        )
        con.execute(
            "INSERT INTO deliverables (deliverable_id, title, deliverable_kind) VALUES (?, ?, ?)",
            ["dlv1", "My memo", "research_memo"],
        )
        con.execute(
            "INSERT INTO deliverable_sections (section_id, deliverable_id, section_index, "
            "title, prose_text) VALUES (?, ?, ?, ?, ?)",
            ["sec1", "dlv1", 0, "Findings", "OPERATOR PROSE"],
        )
        con.execute(
            "INSERT INTO section_blocks (section_id, block_kind, block_id, block_index) "
            "VALUES (?, ?, ?, ?)",
            ["sec1", "claim", "cl1", 0],
        )
    finally:
        con.close()


def test_deliverable_export_resolves_refs_and_cite_onlys(tmp_path):
    db = str(tmp_path / "g.duckdb")
    _seed(db)
    source = mod.resolve_deliverable_export("dlv1", db_path=db)
    assert source is not None
    sec = source.export.sections[0]
    kinds = [b.block_kind for b in sec.blocks]
    assert "synthesized" in kinds and "claim" in kinds  # prose + resolved ref

    claim_block = next(b for b in sec.blocks if b.block_kind == "claim")
    assert claim_block.content_class == "personal_reading"  # REPORTED, not pre-filtered
    assert claim_block.text == "SECRET DELIVERABLE TEXT"

    # End-to-end: adapt_deliverable cite-only's the non-servable claim.
    from services.html_projection.adapters.deliverable import adapt_deliverable
    from services.html_projection.context import RenderContext
    from services.html_projection.renderer import render

    html = render(adapt_deliverable(source.export), RenderContext())
    assert "OPERATOR PROSE" in html
    assert "SECRET DELIVERABLE TEXT" not in html  # cite-only'd, no leak
