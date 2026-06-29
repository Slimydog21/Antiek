"""SPR-06: notebook EXPORT adapter — self-contained, rights-filtered doc-model.

The container path's leak surface IS the doc-model (it now carries resolved
content), so the personal_reading assertion checks both the serialized
doc-model and the rendered HTML — and the full container bytes.
"""

from __future__ import annotations

import json

from services.html_projection.adapters.notebook import ResolvedRefData
from services.html_projection.adapters.notebook_export import adapt_notebook_for_export
from services.html_projection.context import RenderContext
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from services.html_projection.renderer import render

CLAIM = {"type": "antiek_claim_card", "attrs": {"claim_id": "c1"}}
NOTE_PR = {"type": "antiek_note", "attrs": {"note_id": "n1"}}
NOTE_DEL = {"type": "antiek_note", "attrs": {"note_id": "ndel"}}
NOTE_MISSING = {"type": "antiek_note", "attrs": {"note_id": "nmiss"}}
PROSE = {"type": "paragraph", "content": [{"type": "text", "text": "Plain prose."}]}

REFS = {
    "c1": ResolvedRefData(
        kind="claim", content_class="public_domain", ip_holder_id=None,
        title="On Liberty", payload={"statement": "REAL CLAIM TEXT"},
    ),
    "n1": ResolvedRefData(
        kind="note", content_class="personal_reading", ip_holder_id="pg",
        title="A PG essay", payload={"body": "SECRET PASSAGE TEXT"},
    ),
    "ndel": ResolvedRefData(
        kind="note", content_class="public_domain", ip_holder_id=None,
        title="Gone", payload={"body": "GONE"}, deleted_at="2026-06-01",
    ),
}


def _nb(nodes):
    return {"type": "doc", "content": nodes}


def test_servable_ref_is_inlined_no_ref_id():
    dm = adapt_notebook_for_export(_nb([CLAIM]), title="t", resolved_refs=REFS)
    blob = json.dumps(dm)
    assert "REAL CLAIM TEXT" in blob
    assert "claim_id" not in blob  # self-contained: no ref ids remain


def test_personal_reading_is_cite_only_no_leak_anywhere():
    dm = adapt_notebook_for_export(_nb([NOTE_PR]), title="t", resolved_refs=REFS)
    assert "SECRET PASSAGE TEXT" not in json.dumps(dm)  # not in the doc-model
    assert "cite-only" in json.dumps(dm)
    assert "pg" in json.dumps(dm)
    html = render(dm, RenderContext())
    assert "SECRET PASSAGE TEXT" not in html  # not in the rendered HTML


def test_deleted_and_missing_refs_become_visible_markers():
    dm = adapt_notebook_for_export(
        _nb([NOTE_DEL, NOTE_MISSING]), title="t", resolved_refs=REFS
    )
    blob = json.dumps(dm)
    assert "GONE" not in blob
    assert "unavailable" in blob and "2026-06-01" in blob  # deleted marker w/ date


def test_non_ref_nodes_kept_verbatim():
    dm = adapt_notebook_for_export(_nb([PROSE]), title="t", resolved_refs=REFS)
    assert dm["content"][0] == PROSE


def test_export_doc_model_is_self_contained_and_gate_clean():
    dm = adapt_notebook_for_export(
        _nb([CLAIM, NOTE_PR, PROSE]), title="t", resolved_refs=REFS
    )
    # renders identically offline (resolver=None) since there are no refs
    assert_script_free(render(dm, RenderContext()))
    assert extract_island(render(dm, RenderContext())) == dm


def test_full_container_export_does_not_leak(tmp_path):
    # End-to-end: pre-resolve -> emit a signed .antiek; the passage must be
    # absent from the container bytes.
    from services.antiek_format import read_antiek
    from services.antiek_format.signature import ensure_keypair
    from services.html_projection.routing_map import ExportItem, emit

    dm = adapt_notebook_for_export(_nb([CLAIM, NOTE_PR]), title="Nb", resolved_refs=REFS)
    kp = ensure_keypair("u", db_path=str(tmp_path / "k.duckdb"))
    item = ExportItem(
        content_tiptap={"type": "doc", "content": dm["content"]},
        title="Nb",
        document_id="doc-nb",
        user_id="u",
        notebook_id="nb",
        content_class="notebook",
    )
    blob = emit(item, "antiek", keypair=kp)
    assert read_antiek(blob).signature_valid is True
    assert b"SECRET PASSAGE TEXT" not in blob  # rights hold through the container
