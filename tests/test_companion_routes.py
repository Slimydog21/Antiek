"""Companion + evidence-base route proofs (companions SPR-02).

FastAPI TestClient against a REAL DuckDB fixture + a real event log (the
test_companions.py fixture shape): the companion GET renders the narrative
with every claim's data-evidence-id and the honesty headers; the evidence
GET resolves claim+evidence+process by stable id; a tombstoned id resolves
honestly; a second owner gets 404s; project scope answers 501-honest; query
filters compose; the export lands beside the research artifacts with the
honesty header. The auth middleware's enforcement-disabled default stamps
"__operator__" unless a test re-keys a row at the store layer.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.schema import init_highlights_schema
from substrate.books.reading_state import ReadingStateStore
from substrate.companions.evidence_index import read_scope, resolve
from substrate.diligence.store import DiligenceStore
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path

OWNER = "__operator__"
BODY_TEXT = "The companion fixture book opens with a servable sentence worth keeping."


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _write_thread(events_dir: str, investigation_id: str, terminal: str | None = None) -> None:
    from datetime import UTC, datetime

    when = datetime.now(UTC)
    rows = [
        {
            "event_id": f"evt-{investigation_id}-start",
            "investigation_id": investigation_id,
            "action_type": "investigation.start_requested",
            "emitted_at": when.isoformat(),
            "payload": {
                "action_type": "investigation.start_requested",
                "question": f"the question of {investigation_id}",
            },
        }
    ]
    if terminal:
        rows.append(
            {
                "event_id": f"evt-{investigation_id}-terminal",
                "investigation_id": investigation_id,
                "action_type": terminal,
                "emitted_at": datetime.now(UTC).isoformat(),
                "payload": {"action_type": terminal},
            }
        )
    with open(Path(events_dir) / f"{investigation_id}.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _seed(api_env, document_id: str = "doc-1") -> None:
    """The companion fixture: a servable document + grounded nodes + one
    anchor linking inv-1 + a diligence flag + a reading position."""
    db = api_env["db"]
    with connect_write(db, purpose="test/seed-companion-api") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Companion Fixture",
            raw_text=BODY_TEXT,
            content_class="public_domain",
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, 0, 'Page 1', ?, 8)",
            [f"c-{document_id}", document_id, BODY_TEXT],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES (?, 'the first fixture finding', 'insight', 'depth'), "
            "(?, 'the fixture open question', 'question', 'depth')",
            [f"n-1-{document_id}", f"n-2-{document_id}"],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) VALUES "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, 'inv-1', 'depth'), "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, 'inv-1', 'depth')",
            [
                f"e-1-{document_id}", f"n-1-{document_id}", f"n-1-{document_id}",
                f"c-{document_id}", document_id,
                f"e-2-{document_id}", f"n-2-{document_id}", f"n-2-{document_id}",
                f"c-{document_id}", document_id,
            ],
        )
        init_highlights_schema(con)
        con.execute(
            "INSERT INTO anchored_highlights (anchor_id, owner_user_id, "
            "document_id, normalization, anchor_node_id, "
            "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, "
            "servable_at_pin, anchor_quote, anchor_prefix, anchor_suffix, "
            "selection_text_sha256, page_index_hint, source, status, "
            "investigation_id) "
            "VALUES (?, ?, ?, 'unicode-nfc-v1', ?, ?, 0, 11, TRUE, "
            "'the opening', '', '', ?, 0, 'pin', 'active', 'inv-1')",
            [
                f"ahl-{document_id}", OWNER, document_id, f"c-{document_id}",
                hashlib.sha256(BODY_TEXT.encode()).hexdigest(),
                hashlib.sha256(b"the opening").hexdigest(),
            ],
        )
        DiligenceStore().create_flag(
            con,
            owner_user_id=OWNER,
            kind="concept",
            object_ref="the companion fixture concept",
            note=None,
            source_investigation_id="inv-1",
            source_document_id=document_id,
        )
        ReadingStateStore().put(
            con,
            owner_user_id=OWNER,
            document_id=document_id,
            page_index=1,
            anchor_ref=None,
            prefs_json="{}",
            expected_revision=0,
        )
    _write_thread(api_env["events"], "inv-1")
    _write_thread(api_env["events"], "inv-2")


# ── Proof 1: the companion GET + the evidence resolution ───────────────────


def test_companion_get_renders_narrative_with_evidence_ids_and_headers(api_env) -> None:
    _seed(api_env)
    client = _client()

    resp = client.get("/documents/doc-1/companion")
    assert resp.status_code == 200
    assert resp.headers["x-antiek-companion-generated"] == "true"
    assert resp.headers["x-antiek-document-id"] == "doc-1"
    assert resp.headers["x-antiek-rebuilt-at"]
    html = resp.text
    assert "The Companion Fixture" in html
    assert "the first fixture finding" in html  # servable: claim text renders

    # Every rendered evidence id resolves to a real index row.
    rendered_ids = re.findall(r'data-evidence-id="(ev-[0-9a-f]+)"', html)
    assert rendered_ids
    con = connect_read(api_env["db"])
    try:
        rows = read_scope(con, owner_user_id=OWNER, scope="document", scope_id="doc-1")
        for eid in rendered_ids:
            assert resolve(con, eid) is not None, f"dangling rendered id: {eid}"
    finally:
        con.close()
    assert len(rendered_ids) == len(rows)

    # The structured payload (the sanctioned rendering input) mirrors it.
    payload = client.get("/documents/doc-1/companion?format=json").json()
    assert payload["document_id"] == "doc-1"
    assert payload["servable"] is True
    assert {c["evidence_id"] for c in payload["claims"]} <= set(rendered_ids)
    assert payload["processes"], "the reading thread + inv-1 process rows"


def test_evidence_get_resolves_claim_evidence_and_process(api_env) -> None:
    _seed(api_env)
    client = _client()
    client.get("/documents/doc-1/companion")  # rebuild + populate the index
    con = connect_read(api_env["db"])
    try:
        rows = read_scope(con, owner_user_id=OWNER, scope="document", scope_id="doc-1")
    finally:
        con.close()
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r.kind, []).append(r)

    insight = next(r for r in by_kind["claim"] if "node:n-1-doc-1" in r.refs)
    claim = client.get(f"/evidence/{insight.evidence_id}").json()
    assert claim["claim"]["text"] == "the first fixture finding"
    assert claim["claim"]["node_ref"].startswith("node:")
    assert claim["note"] is None

    evidence = client.get(f"/evidence/{by_kind['evidence'][0].evidence_id}").json()
    assert evidence["evidence"]["status"] == "active"

    process = client.get(f"/evidence/{by_kind['process'][0].evidence_id}").json()
    assert process["process"]["status_line"]

    assert client.get("/evidence/ev-never-projected").status_code == 404


def test_tombstoned_id_resolves_honestly(api_env) -> None:
    _seed(api_env)
    client = _client()
    client.get("/documents/doc-1/companion")
    con = connect_read(api_env["db"])
    try:
        claim = next(
            r for r in read_scope(con, owner_user_id=OWNER, scope="document", scope_id="doc-1")
            if r.kind == "claim"
        )
    finally:
        con.close()

    # The claim's source node vanishes; the next rebuild tombstones the row.
    node_ref = next(r for r in claim.refs if r.startswith("node:"))
    with connect_write(api_env["db"], purpose="test/vanish") as con:
        con.execute("DELETE FROM edges WHERE source_node_id = ?", [node_ref[5:]])
        con.execute("DELETE FROM nodes WHERE node_id = ?", [node_ref[5:]])
    client.get("/documents/doc-1/companion")

    resp = client.get(f"/evidence/{claim.evidence_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tombstone"] is True
    assert "honest tombstone" in body["note"]
    assert body["refs"] == list(claim.refs)  # never re-pointed


def test_second_owner_gets_404s(api_env) -> None:
    _seed(api_env)
    client = _client()
    client.get("/documents/doc-1/companion")
    con = connect_read(api_env["db"])
    try:
        first = read_scope(con, owner_user_id=OWNER, scope="document", scope_id="doc-1")[0]
    finally:
        con.close()

    # Re-key the document + the row to a different owner at the store layer.
    with connect_write(api_env["db"], purpose="test/rekey") as con:
        con.execute("UPDATE documents SET owner_user_id = 'someone-else' WHERE document_id = 'doc-1'")
        con.execute(
            "UPDATE evidence_index SET owner_user_id = 'someone-else' WHERE evidence_id = ?",
            [first.evidence_id],
        )

    assert client.get("/documents/doc-1/companion").status_code == 404
    assert client.get(f"/evidence/{first.evidence_id}").status_code == 404


def test_project_scope_answers_honestly_unavailable(api_env) -> None:
    _seed(api_env)
    client = _client()
    for path in ("/projects/ws-1/companion", "/projects/ws-1/evidence"):
        resp = client.get(path)
        assert resp.status_code == 501
        assert "project_scope_unavailable" in resp.json()["detail"]


def test_query_filters_compose(api_env) -> None:
    _seed(api_env)
    client = _client()
    client.get("/documents/doc-1/companion")
    claims = client.get("/documents/doc-1/evidence?kind=claim").json()
    assert claims["count"] == 2
    assert all(r["kind"] == "claim" for r in claims["rows"])
    filtered = client.get("/documents/doc-1/evidence?kind=claim&q=n-2-doc-1").json()
    assert filtered["count"] == 1
    assert "node:n-2-doc-1" in filtered["rows"][0]["refs"]
    bad = client.get("/documents/doc-1/evidence?kind=made_up")
    assert bad.status_code == 422


# ── Proof 2: the export + bounded reads ─────────────────────────────────────


def test_export_lands_beside_artifacts_with_the_honesty_header(api_env) -> None:
    _seed(api_env)
    client = _client()
    resp = client.get("/documents/doc-1/companion")
    assert resp.status_code == 200
    exported = Path(api_env["arts"]) / "companions" / "doc-1.html"
    assert exported.exists()
    text = exported.read_text(encoding="utf-8")
    assert text.startswith("<!-- generated: never authored")
    assert "rebuilt_at:" in text
    assert "edit the sources, never this file" in text


def test_no_full_table_scans_in_the_handler() -> None:
    """The bounded-reads proof, structural: the router's queries are all
    scope/id-filtered; no unbounded SELECT, no unbounded file read."""
    src = Path(
        __file__
    ).resolve().parent.parent / "interfaces" / "research" / "api" / "companion_routes.py"
    text = src.read_text()
    assert "SELECT *" not in text
    assert "read_text(" not in text
    # Every read is filtered: the owner filter, the node/anchor id lookups,
    # and the scope read (the store's WHERE lives in evidence_index.py).
    assert "WHERE document_id = ?" in text  # the owner boundary
    assert "WHERE node_id = ?" in text
    assert "WHERE anchor_id = ?" in text
    store_src = src.parents[3] / "substrate" / "companions" / "evidence_index.py"
    store_text = store_src.read_text()
    assert "WHERE owner_user_id = ? AND scope = ? AND scope_id = ?" in store_text


# ── Honest empty states ─────────────────────────────────────────────────────


def test_empty_document_renders_honest_empty_states(api_env) -> None:
    # A document with NO material at all (no nodes, anchors, flags, position).
    with connect_write(api_env["db"], purpose="test/seed-bare") as con:
        insert_document(
            con,
            document_id="doc-bare",
            source_tier=2,
            document_type="book",
            title="A Bare Book",
            raw_text="bare",
            content_class="public_domain",
            on_conflict="ignore",
        )
    client = _client()
    resp = client.get("/documents/doc-bare/companion")
    assert resp.status_code == 200
    assert "No findings yet." in resp.text
    assert "No anchored passages yet." in resp.text
    assert resp.headers["x-antiek-rebuilt-at"]
    payload = client.get("/documents/doc-bare/companion?format=json").json()
    assert payload["claims"] == []
    assert payload["anchors"] == []
