"""Tests for Sprint 15 API additions: section prose update +
promote-to-graph + deliverable export."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.schemas import TYPED_PAYLOAD_ACTION_TYPES, ActionType


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sprint15-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _make_deliverable_with_section(client) -> tuple[str, str]:
    d = client.post("/deliverables", json={
        "title": "Memo", "deliverable_kind": "research_memo",
    }).json()
    s = client.post("/sections", json={
        "deliverable_id": d["deliverable_id"], "section_index": 0,
        "title": "Intro",
    }).json()
    return d["deliverable_id"], s["section_id"]


# ─────────────────────────────────────────────────────────────────────
# 1. Schema: CLAIM_ASSERTED_BY_OPERATOR
# ─────────────────────────────────────────────────────────────────────


def test_new_action_type_in_typed_set():
    assert ActionType.CLAIM_ASSERTED_BY_OPERATOR.value in TYPED_PAYLOAD_ACTION_TYPES


def test_claim_asserted_payload_round_trip():
    from substrate.schemas import ClaimAssertedByOperatorPayload
    p = ClaimAssertedByOperatorPayload(
        deliverable_id="dlv-1",
        section_id="sec-1",
        claim_text="The operator says X.",
        original_text="The model said Y.",
        cited_chunk_ids=["chunk-1", "chunk-2"],
    )
    assert p.action_type == ActionType.CLAIM_ASSERTED_BY_OPERATOR
    assert p.source_tier == 5  # default
    raw = p.model_dump()
    assert raw["claim_text"] == "The operator says X."


# ─────────────────────────────────────────────────────────────────────
# 2. PATCH /sections/{id}/prose — save without promote
# ─────────────────────────────────────────────────────────────────────


def test_patch_prose_saves_without_promote(temp_substrate):
    import duckdb
    client = _client(temp_substrate)
    _, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "Edited prose for the section.", "original_text": ""},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "saved"
    assert body["claim_node_id"] is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (prose,) = con.execute(
            "SELECT prose_text FROM deliverable_sections WHERE section_id = ?",
            [sid],
        ).fetchone()
    finally:
        con.close()
    assert prose == "Edited prose for the section."


def test_patch_prose_404_for_unknown_section(temp_substrate):
    client = _client(temp_substrate)
    resp = client.patch(
        "/sections/sec-nope/prose",
        json={"prose_text": "x", "original_text": ""},
    )
    assert resp.status_code == 404


def test_patch_prose_empty_rejected(temp_substrate):
    client = _client(temp_substrate)
    _, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "", "original_text": ""},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# 3. PATCH with promote_to_graph=True
# ─────────────────────────────────────────────────────────────────────


def test_patch_prose_promote_writes_claim_node_and_event(temp_substrate):
    import duckdb
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={
            "prose_text": "The substrate compounds nonlinearly.\nThis is operator-asserted.",
            "original_text": "",
            "promote_to_graph": True,
            "cited_chunk_ids": ["chunk-A", "chunk-B"],
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "saved_and_promoted"
    assert body["claim_node_id"] is not None
    assert body["claim_event_id"] is not None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (node_type, metadata,) = con.execute(
            "SELECT node_type, metadata FROM nodes WHERE node_id = ?",
            [body["claim_node_id"]],
        ).fetchone()
    finally:
        con.close()
    assert node_type == "claim"
    import json
    md = json.loads(metadata)
    assert md["source"] == "operator_asserted"
    assert md["deliverable_id"] == did
    assert md["section_id"] == sid
    assert md["policy_id"] == f"operator/{did}"


def test_patch_prose_promote_emits_claim_asserted_event(temp_substrate):
    """The CLAIM_ASSERTED_BY_OPERATOR event must land in the event log."""
    import glob
    import json
    client = _client(temp_substrate)
    _, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={
            "prose_text": "Operator-asserted claim text here.",
            "original_text": "",
            "promote_to_graph": True,
        },
    )
    body = resp.json()
    # Walk events dir for the event id we got back
    event_files = glob.glob(
        os.path.join(temp_substrate["events_dir"], "**", "*.jsonl"),
        recursive=True,
    )
    found = False
    for ef in event_files:
        with open(ef) as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("event_id") == body["claim_event_id"]:
                    assert ev["action_type"] == ActionType.CLAIM_ASSERTED_BY_OPERATOR.value
                    found = True
    assert found, f"event {body['claim_event_id']} not in {event_files}"


# ─────────────────────────────────────────────────────────────────────
# 4. GET /deliverables/{id}/export
# ─────────────────────────────────────────────────────────────────────


def test_export_markdown_includes_title_and_sections(temp_substrate):
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "Intro prose.", "original_text": ""},
    )
    resp = client.get(f"/deliverables/{did}/export?format=markdown")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "markdown"
    assert "# Memo" in body["content"]
    assert "## Intro" in body["content"]
    assert "Intro prose." in body["content"]
    assert body["filename"].endswith(".md")


def test_edit_round_trip_reload_and_export_agree(temp_substrate):
    """SPR-02: a saved manual /write edit survives BOTH reads the operator
    ships from — the reload re-fetch (GET /deliverables/{id}) AND the export
    (GET /deliverables/{id}/export). Both read
    ``deliverable_sections.prose_text`` (app.py:2573 and :2890), the same
    column PATCH /sections/{id}/prose writes (:2801) — so there is no column
    mismatch where one read sees the edit and the other doesn't. The /write
    editor now reaches this PATCH via updateSectionProse (Outline SPR-02); this
    proves the persisted edit is durable on both surfaces, not just one."""
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)

    # The manual edit the /write editor persists (was silently dropped before
    # the onContentChange wiring — the Outline mount had no handler).
    edited = "The operator sharpened this thesis by hand — keep it."
    resp = client.patch(
        f"/sections/{sid}/prose", json={"prose_text": edited, "original_text": ""}
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "saved"

    # Direction 1 — reload re-fetch (what a page reload calls).
    detail = client.get(f"/deliverables/{did}")
    assert detail.status_code == 200
    section = next(
        s for s in detail.json()["sections"] if s["section_id"] == sid
    )
    assert section["prose_text"] == edited

    # Direction 2 — export path (what the operator ships from).
    export = client.get(f"/deliverables/{did}/export?format=markdown")
    assert export.status_code == 200
    assert edited in export.json()["content"]


def test_export_html_escapes_content(temp_substrate):
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "Has <script>alert(1)</script> in prose.", "original_text": ""},
    )
    resp = client.get(f"/deliverables/{did}/export?format=html")
    body = resp.json()
    assert body["format"] == "html"
    assert "<!doctype html>" in body["content"]
    assert "&lt;script&gt;" in body["content"]
    assert "<script>alert(1)</script>" not in body["content"]


def test_export_json_returns_structured_bundle(temp_substrate):
    import json
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose", json={"prose_text": "Prose", "original_text": ""},
    )
    resp = client.get(f"/deliverables/{did}/export?format=json")
    body = resp.json()
    bundle = json.loads(body["content"])
    assert bundle["deliverable_id"] == did
    assert bundle["title"] == "Memo"
    assert len(bundle["sections"]) == 1
    assert bundle["sections"][0]["prose_text"] == "Prose"


def test_export_unsupported_format_422(temp_substrate):
    """Format outside the SUPPORTED tuple returns 422. Sprint 15 §3.4
    landed PDF/EPUB/Substack, so the test asserts a truly unknown
    format (``xml``) rejects — not PDF, which is now supported."""
    client = _client(temp_substrate)
    did, _ = _make_deliverable_with_section(client)
    resp = client.get(f"/deliverables/{did}/export?format=xml")
    assert resp.status_code == 422
    assert "format must be one of" in resp.json()["detail"]


def test_export_404_for_unknown_deliverable(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/deliverables/dlv-nope/export?format=markdown")
    assert resp.status_code == 404


def test_export_substack_omits_h1_title_and_uses_blockquote_kind(temp_substrate):
    """Substack import flow injects its own H1 from the post title field,
    so the substack-flavored markdown variant deliberately omits the
    leading ``# {title}`` line that the standard markdown export emits."""
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "Substack-ready prose with em-dashes — preserved.", "original_text": ""},
    )
    resp = client.get(f"/deliverables/{did}/export?format=substack")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "substack"
    assert body["content_encoding"] == "text"
    assert body["filename"].endswith(".substack.md")
    # No leading `# Memo` H1
    assert not body["content"].lstrip().startswith("# ")
    # Kind label in blockquote, not paragraph
    assert "> _" in body["content"]
    # Em-dashes preserved verbatim
    assert "em-dashes — preserved" in body["content"]


def test_export_pdf_returns_base64_pdf_bytes(temp_substrate):
    """PDF export — Sprint 15 §3.4. xhtml2pdf renders the researcher's-
    notebook stylesheet to base64-encoded PDF bytes. Verifies the
    response shape + that the decoded bytes start with the PDF magic
    number (``%PDF-``)."""
    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip("xhtml2pdf not installed — pip install -e '.[export]'")
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose", json={"prose_text": "Body text.", "original_text": ""}
    )
    resp = client.get(f"/deliverables/{did}/export?format=pdf")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "pdf"
    assert body["content_encoding"] == "base64"
    assert body["filename"].endswith(".pdf")
    import base64
    decoded = base64.b64decode(body["content"])
    # PDF files start with the byte sequence ``%PDF-`` (0x25 0x50 0x44 0x46 0x2D).
    assert decoded.startswith(b"%PDF-"), f"got {decoded[:8]!r}"
    # Sanity: PDF length is non-trivial — a real-rendered one-section
    # document is at least a few hundred bytes.
    assert len(decoded) > 500


def test_export_epub_returns_base64_epub_zip(temp_substrate):
    """EPUB export — Sprint 15 §3.4. ebooklib produces a ZIP file with
    the EPUB MIME marker. Verifies response shape + ZIP magic number."""
    try:
        import ebooklib  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip("ebooklib not installed — pip install -e '.[export]'")
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose", json={"prose_text": "Chapter prose.", "original_text": ""}
    )
    resp = client.get(f"/deliverables/{did}/export?format=epub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "epub"
    assert body["content_encoding"] == "base64"
    assert body["filename"].endswith(".epub")
    import base64
    decoded = base64.b64decode(body["content"])
    # EPUB is a ZIP file — starts with the ZIP local file header magic
    # bytes ``PK\x03\x04``.
    assert decoded.startswith(b"PK\x03\x04"), f"got {decoded[:8]!r}"
    # EPUB requires an ``mimetype`` entry as the first uncompressed file
    # containing ``application/epub+zip``. ebooklib writes this correctly.
    assert b"application/epub+zip" in decoded[:1024]
