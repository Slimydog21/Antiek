"""M6: tombstone + ref-resolution semantics tests (HPRJ SPR-02).

A deleted ref renders the SAME tombstone the live notebook surface shows.
A missing/deleted ref is never a crash, never a silent drop. The tombstone
contract mirrors substrate/notebooks/__init__.py lines 20-21: "This claim
was deleted on YYYY-MM-DD; prior text was...".
"""

from __future__ import annotations

import re

import pytest

from services.html_projection import (
    DictRefResolver,
    Provenance,
    RenderContext,
    ResolvedRef,
    Tombstone,
    render,
)


def _body(html: str) -> str:
    """Strip the inlined <style> block so class-name assertions check
    the rendered body, not the CSS class definitions."""
    return re.sub(r"<style>.*?</style>", "", html, flags=re.DOTALL)


def _ctx_with_resolver(
    refs: dict | None = None,
) -> RenderContext:
    return RenderContext(
        resolver=DictRefResolver(refs or {}),
        provenance=Provenance(document_id="doc-t-1", rendered_at="2026-05-21T12:00:00Z"),
    )


# ── Missing ref (no resolver / ref not found) → tombstone, no crash ──


def test_missing_ref_renders_tombstone_no_crash():
    """A ref-bearing block with no resolver attached renders a
    'could not be resolved' tombstone. Never a crash, never a silent
    drop."""
    ctx = RenderContext()  # no resolver
    doc = {
        "content": [
            {"type": "antiek_claim_card", "attrs": {"block_id": "b1", "claim_id": "clm-missing"}},
        ]
    }
    html = render(doc, ctx)
    body = _body(html)
    assert "antiek-tombstone" in body
    assert "could not be resolved" in body
    assert "clm-missing" in body


def test_missing_ref_renders_tombstone_with_resolver_not_found():
    """A ref not in the resolver's map renders the 'could not be
    resolved' tombstone (missing, not deleted)."""
    ctx = _ctx_with_resolver({})
    doc = {
        "content": [
            {"type": "antiek_note", "attrs": {"block_id": "b1", "note_id": "nte-404"}},
        ]
    }
    html = render(doc, ctx)
    assert "could not be resolved" in html
    assert "nte-404" in html
    # Distinct from the deleted case — no "deleted on" wording.
    assert "was deleted on" not in html


# ── Deleted ref → tombstone with deletion date + prior text ──


def test_deleted_ref_renders_tombstone_with_date_and_prior_text():
    """A deleted ref (resolver returns a Tombstone with deleted_at)
    renders the SAME tombstone the live notebook surface shows:
    'This <kind> was deleted on <date>; prior text was <text>.'"""
    ctx = _ctx_with_resolver(
        {
            ("claim_card", "clm-deleted"): Tombstone(
                kind="claim",
                deleted_at="2026-03-15",
                prior_text="the original claim",
                ref_id="clm-deleted",
            )
        }
    )
    doc = {
        "content": [
            {"type": "antiek_claim_card", "attrs": {"block_id": "b1", "claim_id": "clm-deleted"}},
        ]
    }
    html = render(doc, ctx)
    assert "This claim was deleted on 2026-03-15" in html
    assert "prior text was" in html
    assert "the original claim" in html


def test_deleted_ref_no_prior_text_omits_prior_clause():
    """A deleted ref with no prior_text omits the 'prior text was'
    clause (honest about what the substrate retained)."""
    ctx = _ctx_with_resolver(
        {
            ("note", "nte-del"): Tombstone(
                kind="note",
                deleted_at="2026-01-01",
                prior_text=None,
                ref_id="nte-del",
            )
        }
    )
    doc = {
        "content": [
            {"type": "antiek_note", "attrs": {"block_id": "b1", "note_id": "nte-del"}},
        ]
    }
    html = render(doc, ctx)
    assert "This note was deleted on 2026-01-01" in html
    assert "prior text was" not in html


# ── Tombstone consistency: same ref → same tombstone ──


def test_same_deleted_ref_renders_same_tombstone():
    """The tombstone for a given deleted ref is byte-stable across
    renders (consistency contract: the live surface and the projection
    agree)."""
    refs = {
        ("claim_card", "clm-1"): Tombstone(
            kind="claim", deleted_at="2026-02-20", prior_text="x", ref_id="clm-1"
        )
    }
    doc = {
        "content": [
            {"type": "antiek_claim_card", "attrs": {"block_id": "b1", "claim_id": "clm-1"}},
        ]
    }
    a = render(doc, _ctx_with_resolver(refs))
    b = render(doc, _ctx_with_resolver(refs))
    assert a == b


# ── Every ref-bearing block type honors the tombstone contract ──


@pytest.mark.parametrize(
    "block_type,tiptap_type,ref_attr,ref_id",
    [
        ("claim_card", "antiek_claim_card", "claim_id", "clm-1"),
        ("region_embed", "antiek_region_embed", "document_id", "doc-r-1"),
        ("note", "antiek_note", "note_id", "nte-1"),
        ("question_card", "antiek_question_card", "question_id", "qst-1"),
        ("cross_doc_link", "antiek_cross_doc_link", "source_document_id", "doc-src-1"),
        ("chat_exchange", "antiek_chat_exchange", "exchange_id", "xch-1"),
        ("master_md_section", "antiek_master_md_section", "synthesis_id", "syn-1"),
        ("image", "antiek_image", "image_id", "img-1"),
    ],
)
def test_every_ref_block_renders_tombstone_when_missing(
    block_type, tiptap_type, ref_attr, ref_id
):
    """Every ref-bearing block type renders a tombstone when its ref is
    missing (no silent drop, no crash). Covers the full ref-bearing
    taxonomy."""
    ctx = _ctx_with_resolver({})  # empty → all refs missing
    doc = {
        "content": [
            {"type": tiptap_type, "attrs": {"block_id": "b1", ref_attr: ref_id}},
        ]
    }
    html = render(doc, ctx)
    body = _body(html)
    assert "antiek-tombstone" in body
    assert "could not be resolved" in body


@pytest.mark.parametrize(
    "block_type,tiptap_type,ref_attr,ref_id",
    [
        ("claim_card", "antiek_claim_card", "claim_id", "clm-1"),
        ("region_embed", "antiek_region_embed", "document_id", "doc-r-1"),
        ("note", "antiek_note", "note_id", "nte-1"),
        ("question_card", "antiek_question_card", "question_id", "qst-1"),
        ("chat_exchange", "antiek_chat_exchange", "exchange_id", "xch-1"),
        ("master_md_section", "antiek_master_md_section", "synthesis_id", "syn-1"),
        ("image", "antiek_image", "image_id", "img-1"),
    ],
)
def test_every_ref_block_renders_resolved_content(
    block_type, tiptap_type, ref_attr, ref_id
):
    """Every ref-bearing block type renders the resolved substrate
    content when the ref resolves (not the tombstone)."""
    payload_key = {
        "claim_card": "statement", "region_embed": "passage_text",
        "note": "body", "question_card": "question",
        "chat_exchange": "turns", "master_md_section": "body",
        "image": "alt",
    }[block_type]
    payload_val = {
        "statement": "resolved claim text",
        "passage_text": "resolved region text",
        "body": "resolved body",
        "question": "resolved question?",
        "turns": [{"role": "user", "text": "resolved turn"}],
        "alt": "resolved alt",
    }[payload_key]
    ctx = _ctx_with_resolver(
        {
            (block_type, ref_id): ResolvedRef(
                kind=block_type, payload={payload_key: payload_val}
            )
        }
    )
    doc = {
        "content": [
            {"type": tiptap_type, "attrs": {"block_id": "b1", ref_attr: ref_id}},
        ]
    }
    html = render(doc, ctx)
    body = _body(html)
    assert "antiek-tombstone" not in body
    assert "resolved" in body


# ── Tombstone never crashes on hostile ref_id ──


def test_tombstone_escapes_hostile_ref_id():
    """A hostile ref_id (with <, >, &) is escaped in the tombstone — no
    markup injection through the ref_id."""
    ctx = _ctx_with_resolver({})
    doc = {
        "content": [
            {"type": "antiek_claim_card", "attrs": {"block_id": "b1", "claim_id": "<script>x</script>"}},
        ]
    }
    html = render(doc, ctx)
    assert "<script>x</script>" not in html  # not unescaped
    assert "&lt;script&gt;" in html  # escaped


# ── Tombstone matches live surface wording (consistency contract) ──


def test_tombstone_wording_matches_live_notebook_surface():
    """The tombstone wording matches the live notebook surface's contract
    (substrate/notebooks/__init__.py:20-21: 'This claim was deleted on
    YYYY-MM-DD; prior text was...'). A reader comparing the live surface
    and a projection sees the same tombstone."""
    ctx = _ctx_with_resolver(
        {
            ("claim_card", "clm-1"): Tombstone(
                kind="claim",
                deleted_at="2026-04-10",
                prior_text="the prior claim",
                ref_id="clm-1",
            )
        }
    )
    doc = {
        "content": [
            {"type": "antiek_claim_card", "attrs": {"block_id": "b1", "claim_id": "clm-1"}},
        ]
    }
    html = render(doc, ctx)
    # The live surface's wording: "This claim was deleted on YYYY-MM-DD; prior text was..."
    assert "This claim was deleted on 2026-04-10" in html
    assert "prior text was" in html


def test_resolver_returning_tombstone_does_not_crash_renderer():
    """A resolver that returns a Tombstone (rather than raising) for a
    deleted ref → renderer renders the tombstone. The resolver protocol
    forbids raising for missing/deleted refs; this pins that."""
    ctx = _ctx_with_resolver(
        {("image", "img-del"): Tombstone(kind="image", deleted_at="2026-05-01", prior_text=None, ref_id="img-del")}
    )
    doc = {
        "content": [
            {"type": "antiek_image", "attrs": {"block_id": "b1", "image_id": "img-del"}},
        ]
    }
    html = render(doc, ctx)
    assert "This image was deleted on 2026-05-01" in html
