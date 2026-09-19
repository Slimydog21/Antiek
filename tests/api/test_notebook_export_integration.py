"""SPR-06: notebook export wiring — resolve_notebook_export resolves REAL refs.

Proves the full path on real substrate fixture rows (a notebook -> a claim_card
block -> a claim node -> a source document with a content_class): NOT mocked.
This is what validates that the resolved_refs wiring works end-to-end, the gap
the earlier degraded resolved_refs={} left open.
"""

from __future__ import annotations

import json

from interfaces.research.api import notebook_artifact as mod


def _seed(
    db_path: str,
    *,
    notebook_document_id: str | None = None,
    linked_content_class: str = "public_domain",
) -> None:
    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized
    from substrate.notebooks import append_block, create_notebook
    from substrate.notebooks.authority import operator_notebook_authority

    ensure_initialized(db_path)
    con = connect_write(db_path)
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "content_class, ip_holder_id, title) VALUES (?, ?, ?, ?, ?, ?)",
            ["doc1", 1, "article", "public_domain", None, "On Liberty"],
        )
        if notebook_document_id and notebook_document_id != "doc1":
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, ip_holder_id, title) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    notebook_document_id,
                    2,
                    "paper",
                    linked_content_class,
                    "linked-holder",
                    "Linked source",
                ],
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
        authority = operator_notebook_authority("nb1")
        create_notebook(
            con,
            authority,
            title="My notebook",
            document_id=notebook_document_id,
        )
        append_block(
            con,
            authority,
            block_type="claim_card",
            ref_id="c1",
            content={"type": "antiek_claim_card", "attrs": {"claim_id": "c1"}},
        )
    finally:
        con.close()


def test_notebook_export_resolves_real_refs(tmp_path):
    from substrate.notebooks.authority import operator_notebook_authority

    db = str(tmp_path / "graph.duckdb")
    _seed(db)
    source = mod.resolve_notebook_export(operator_notebook_authority("nb1"), db_path=db)
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
    from substrate.notebooks.authority import operator_notebook_authority

    db = str(tmp_path / "g.duckdb")
    ensure_initialized(db)
    assert mod.resolve_notebook_export(operator_notebook_authority("nope"), db_path=db) is None


def test_notebook_export_resolves_twin_note_from_linked_asset(tmp_path):
    from runtime.db_lock import connect_write
    from substrate.engagement_spine import InMemoryEngagementStore
    from substrate.engagement_spine.twin import record_twin_insight
    from substrate.notebooks import append_block
    from substrate.notebooks.authority import operator_notebook_authority

    db = str(tmp_path / "twin-export.duckdb")
    _seed(db, notebook_document_id="paper-1")
    store = InMemoryEngagementStore()
    note = record_twin_insight(
        "paper-1",
        "Cited reuse is the graph's compounding mechanism.",
        store=store,
    )
    with connect_write(db, purpose="test:notebook-twin-export") as con:
        append_block(
            con,
            operator_notebook_authority("nb1"),
            block_type="note",
            ref_id=note.note_id,
            content={"type": "note_block", "attrs": {"note_id": note.note_id}},
        )

    source = mod.resolve_notebook_export(
        operator_notebook_authority("nb1"), db_path=db, engagement_store=store
    )
    assert source is not None
    resolved = source.resolved_refs[note.note_id]
    assert resolved.kind == "insight"
    assert resolved.content_class == "public_domain"
    assert resolved.source_document_id == "paper-1"
    assert resolved.payload["statement"] == note.text

    from services.html_projection.adapters.notebook_export import (
        adapt_notebook_for_export,
    )
    from services.html_projection.context import RenderContext
    from services.html_projection.renderer import render

    doc = adapt_notebook_for_export(
        source.content_tiptap,
        title=source.title,
        resolved_refs=source.resolved_refs,
    )
    html = render(doc, RenderContext())
    assert note.text in html
    assert note.note_id not in html


def test_notebook_export_withholds_twin_text_for_restricted_linked_asset(tmp_path):
    from runtime.db_lock import connect_write
    from substrate.engagement_spine import InMemoryEngagementStore
    from substrate.engagement_spine.twin import record_twin_insight
    from substrate.notebooks import append_block
    from substrate.notebooks.authority import operator_notebook_authority

    db = str(tmp_path / "restricted-twin-export.duckdb")
    _seed(
        db,
        notebook_document_id="restricted-paper",
        linked_content_class="personal_reading",
    )
    store = InMemoryEngagementStore()
    note = record_twin_insight(
        "restricted-paper",
        "Potentially source-derived private wording.",
        store=store,
    )
    with connect_write(db, purpose="test:restricted-notebook-twin-export") as con:
        append_block(
            con,
            operator_notebook_authority("nb1"),
            block_type="note",
            ref_id=note.note_id,
            content={"type": "note_block", "attrs": {"note_id": note.note_id}},
        )

    source = mod.resolve_notebook_export(
        operator_notebook_authority("nb1"), db_path=db, engagement_store=store
    )
    assert source is not None
    assert source.resolved_refs[note.note_id].content_class == "personal_reading"

    from services.html_projection.adapters.notebook_export import (
        adapt_notebook_for_export,
    )
    from services.html_projection.context import RenderContext
    from services.html_projection.renderer import render

    doc = adapt_notebook_for_export(
        source.content_tiptap,
        title=source.title,
        resolved_refs=source.resolved_refs,
    )
    rendered = render(doc, RenderContext())
    assert note.text not in rendered
    assert "cite-only" in rendered
    assert "linked-holder" in rendered


def test_notebook_export_prefers_canonical_twin_ref_over_legacy_cached_text(tmp_path):
    from runtime.db_lock import connect_write
    from substrate.engagement_spine import InMemoryEngagementStore
    from substrate.engagement_spine.twin import record_twin_insight
    from substrate.notebooks import append_block
    from substrate.notebooks.authority import operator_notebook_authority

    db = str(tmp_path / "legacy-twin-export.duckdb")
    _seed(
        db,
        notebook_document_id="restricted-legacy-paper",
        linked_content_class="personal_reading",
    )
    store = InMemoryEngagementStore()
    note = record_twin_insight(
        "restricted-legacy-paper",
        "Current restricted twin text.",
        store=store,
    )
    stale = "STALE CACHED TWIN TEXT MUST NOT EXPORT"
    with connect_write(db, purpose="test:legacy-notebook-twin-export") as con:
        append_block(
            con,
            operator_notebook_authority("nb1"),
            block_type="note",
            ref_id=note.note_id,
            content={"text": stale},
        )

    source = mod.resolve_notebook_export(
        operator_notebook_authority("nb1"), db_path=db, engagement_store=store
    )
    assert source is not None
    assert source.content_tiptap["content"][1] == {
        "type": "note_block",
        "attrs": {"note_id": note.note_id},
    }

    from services.html_projection.adapters.notebook_export import (
        adapt_notebook_for_export,
    )
    from services.html_projection.context import RenderContext
    from services.html_projection.renderer import render

    doc = adapt_notebook_for_export(
        source.content_tiptap,
        title=source.title,
        resolved_refs=source.resolved_refs,
    )
    rendered = render(doc, RenderContext())
    assert stale not in rendered
    assert note.text not in rendered
    assert "cite-only" in rendered
