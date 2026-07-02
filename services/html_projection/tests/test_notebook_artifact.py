"""SPR-06 M2: notebook (Tier-2/3) → artifact — rights resolver + tombstones.

For a notebook the leak surface is the RESOLVER OUTPUT (rendered HTML), not the
island (which carries ref_ids). So the personal_reading assertion checks the
HTML; the island is also checked to confirm it never carried the passage.
"""

from __future__ import annotations

import json

from services.html_projection.adapters.notebook import (
    ResolvedRefData,
    RightsAwareResolver,
    adapt_notebook,
)
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from services.html_projection.renderer import render

CLAIM = {"type": "antiek_claim_card", "attrs": {"claim_id": "c1"}}
NOTE_PR = {"type": "antiek_note", "attrs": {"note_id": "n1"}}
CLAIM_DEL = {"type": "antiek_claim_card", "attrs": {"claim_id": "cdel"}}
CLAIM_MISSING = {"type": "antiek_claim_card", "attrs": {"claim_id": "cmiss"}}
PROSE = {"type": "paragraph", "content": [{"type": "text", "text": "Some prose."}]}

REFS = {
    "c1": ResolvedRefData(
        kind="claim",
        content_class="public_domain",
        ip_holder_id=None,
        title="On Liberty",
        payload={"statement": "REAL CLAIM TEXT"},
    ),
    "n1": ResolvedRefData(
        kind="note",
        content_class="personal_reading",
        ip_holder_id="pg",
        title="A Paul Graham essay",
        payload={"body": "SECRET PASSAGE TEXT"},
    ),
    "cdel": ResolvedRefData(
        kind="claim",
        content_class="public_domain",
        ip_holder_id=None,
        title="Deleted claim",
        payload={"statement": "GONE-CONTENT"},
        deleted_at="2026-06-01",
    ),
}


def _render(nodes, refs=REFS):
    tiptap = {"type": "doc", "content": nodes}
    doc_model, ctx = adapt_notebook(tiptap, title="A notebook", resolved_refs=refs)
    return render(doc_model, ctx), doc_model


def test_servable_claim_renders_its_text():
    html, _ = _render([CLAIM])
    assert "REAL CLAIM TEXT" in html


def test_personal_reading_note_is_cite_only_no_leak():
    html, dm = _render([NOTE_PR])
    assert "SECRET PASSAGE TEXT" not in html  # resolver-output leak surface
    assert "cite-only" in html
    assert "pg" in html  # ip_holder surfaced in the notice
    # The doc-model/island carries only the ref_id — never the passage.
    assert "SECRET PASSAGE TEXT" not in json.dumps(dm)


def test_deleted_ref_renders_tombstone_not_content():
    html, _ = _render([CLAIM_DEL])
    assert "GONE-CONTENT" not in html
    assert "2026-06-01" in html or "deleted" in html.lower()


def test_missing_ref_renders_tombstone_not_crash():
    html, _ = _render([CLAIM_MISSING])
    low = html.lower()
    assert any(m in low for m in ("deleted", "unavailable", "missing", "not available")) \
        or "cmiss" in html


def test_notebook_island_round_trips():
    tiptap = {"type": "doc", "content": [CLAIM, NOTE_PR, PROSE]}
    doc_model, ctx = adapt_notebook(tiptap, title="A notebook", resolved_refs=REFS)
    assert extract_island(render(doc_model, ctx)) == doc_model


def test_notebook_artifact_is_gate_clean():
    html, _ = _render([CLAIM, NOTE_PR, PROSE])
    assert_script_free(html)


def test_rights_resolver_is_baked_into_the_returned_ctx():
    # No caller can render the notebook without the rights filter: the adapter
    # returns the ctx, and its resolver is the rights-aware one.
    _, ctx = adapt_notebook(
        {"type": "doc", "content": [CLAIM]}, title="x", resolved_refs=REFS
    )
    assert isinstance(ctx.resolver, RightsAwareResolver)
