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

from substrate.schemas import ActionType, TYPED_PAYLOAD_ACTION_TYPES


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
        json={"prose_text": "Edited prose for the section."},
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
        json={"prose_text": "x"},
    )
    assert resp.status_code == 404


def test_patch_prose_empty_rejected(temp_substrate):
    client = _client(temp_substrate)
    _, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": ""},
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
            "original_text": "The substrate compounds linearly.",
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
    import json
    import glob
    client = _client(temp_substrate)
    _, sid = _make_deliverable_with_section(client)
    resp = client.patch(
        f"/sections/{sid}/prose",
        json={
            "prose_text": "Operator-asserted claim text here.",
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
        with open(ef, "r") as f:
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
        json={"prose_text": "Intro prose."},
    )
    resp = client.get(f"/deliverables/{did}/export?format=markdown")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "markdown"
    assert "# Memo" in body["content"]
    assert "## Intro" in body["content"]
    assert "Intro prose." in body["content"]
    assert body["filename"].endswith(".md")


def test_export_html_escapes_content(temp_substrate):
    client = _client(temp_substrate)
    did, sid = _make_deliverable_with_section(client)
    client.patch(
        f"/sections/{sid}/prose",
        json={"prose_text": "Has <script>alert(1)</script> in prose."},
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
        f"/sections/{sid}/prose", json={"prose_text": "Prose"},
    )
    resp = client.get(f"/deliverables/{did}/export?format=json")
    body = resp.json()
    bundle = json.loads(body["content"])
    assert bundle["deliverable_id"] == did
    assert bundle["title"] == "Memo"
    assert len(bundle["sections"]) == 1
    assert bundle["sections"][0]["prose_text"] == "Prose"


def test_export_unsupported_format_422(temp_substrate):
    client = _client(temp_substrate)
    did, _ = _make_deliverable_with_section(client)
    resp = client.get(f"/deliverables/{did}/export?format=pdf")
    assert resp.status_code == 422


def test_export_404_for_unknown_deliverable(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/deliverables/dlv-nope/export?format=markdown")
    assert resp.status_code == 404
