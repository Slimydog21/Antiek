"""Read SPR-13 M3 — the filing typed-event handler (the accept path).

The load-bearing invariants (single-writer + suggest-only):
  - Accepting a suggestion emits ``document.filed_into_investigation``, whose
    /events/typed side-effect handler sets ``documents.investigation_id`` THROUGH
    THE FUNNEL (connect_write = runtime/db_lock). After the event, the doc's
    investigation_id IS the chosen project (verified via GET /documents).
  - Filing is a LINK, not a copy: ip_holder_id + the document row are otherwise
    untouched (the §9 chain stays intact).
  - NEVER auto-ships: the documents table is NOT mutated by listing the personal
    space or asking for a suggestion — only by the explicit filing event. (The
    selector-level decline-leaves-it case is covered in test_personal_space.py;
    here we assert no API read path files anything.)
  - A filing for a missing document 404s (nothing filed).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-filing-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _seed_document(db_path, *, document_id, ip_holder_id="ip-1", investigation_id=None):
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="test:seed_doc") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, source_uri, title, "
            "ip_holder_id, investigation_id"
            ") VALUES (?, 3, 'pdf', 'file:///t.pdf', 'A doc', ?, ?)",
            [document_id, ip_holder_id, investigation_id],
        )


def _doc_row(client, document_id):
    body = client.get("/documents").json()
    return next(d for d in body["documents"] if d["document_id"] == document_id)


def _file_event(document_id, investigation_id, *, score=0.7, question="a question"):
    return {
        "investigation_id": investigation_id,
        "document_id": document_id,
        "payload": {
            "action_type": "document.filed_into_investigation",
            "filed_document_id": document_id,
            "target_investigation_id": investigation_id,
            "match_score": score,
            "target_question": question,
        },
        "role": "read/personal_space",
        "policy_id": "read/personal_space/file",
    }


def test_accept_files_doc_into_project_through_funnel(isolated):
    _seed_document(isolated, document_id="doc-1", ip_holder_id="ip-acme")
    client = _client()

    # Before: unfiled.
    assert _doc_row(client, "doc-1")["investigation_id"] is None

    resp = client.post("/events/typed", json=_file_event("doc-1", "inv-target"))
    assert resp.status_code == 201, resp.text
    assert resp.json()["action_type"] == "document.filed_into_investigation"

    after = _doc_row(client, "doc-1")
    # Filed — through the funnel (the only writer).
    assert after["investigation_id"] == "inv-target"
    # LINK, not copy: ip_holder_id immutable.
    assert after["ip_holder_id"] == "ip-acme"


def test_listing_and_suggestion_never_auto_file(isolated):
    _seed_document(isolated, document_id="doc-2")
    client = _client()

    # Reading the personal space + asking for a suggestion must NOT mutate the
    # documents table (NEVER auto-ship — only explicit accept files).
    client.get("/meta-readings")
    # The suggestion endpoint needs the embedder; it may 503 in CI without
    # sentence-transformers — either way it must not file. Tolerate both.
    client.get("/meta-readings/file-suggestion?document_id=doc-2")
    assert _doc_row(client, "doc-2")["investigation_id"] is None


def test_personal_space_discovers_canonical_research_deliverables(isolated):
    from runtime.db_lock import connect_write
    from substrate.engagement_spine import InMemoryEngagementStore
    from substrate.engagement_spine.canonical_commit import commit_reviewed_draft

    model = {
        "title": "[Draft] Canonical collective analysis",
        "content": [
            {
                "type": "paragraph",
                "attrs": {
                    "provenance": {
                        "kind": "source",
                        "parent_asset_id": "source-paper",
                    }
                },
                "content": [{"type": "text", "text": "Canonical analysis."}],
            }
        ],
    }
    draft_sha = hashlib.sha256(
        json.dumps(
            model, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    store = InMemoryEngagementStore()
    store.put_document(
        "draft-canonical-reading",
        {
            "mode": "draft_combined",
            "parent_asset_id": "source-paper",
            "doc_model": model,
            "draft_sha256": draft_sha,
        },
    )
    with connect_write(isolated, purpose="test:canonical_personal_space") as con:
        commit_reviewed_draft(
            con=con,
            engagement_store=store,
            draft_document_id="draft-canonical-reading",
            target_deliverable_id="dlv-canonical-reading",
            expected_revision="new",
            reviewed_draft_sha256=draft_sha,
            create_combined=True,
        )
    response = _client().get("/meta-readings")
    assert response.status_code == 200, response.text
    asset = next(
        item
        for item in response.json()["assets"]
        if item["asset_id"] == "dlv-canonical-reading"
    )
    assert asset == {
        "asset_id": "dlv-canonical-reading",
        "kind": "canonical_research",
        "title": "Canonical collective analysis",
        "prompt": None,
        "document_ids": ["source-paper"],
        "emitted_at": asset["emitted_at"],
        "open_route": "/read/canonical/dlv-canonical-reading",
    }


def test_filing_missing_document_404s_nothing_filed(isolated):
    client = _client()
    resp = client.post("/events/typed", json=_file_event("ghost", "inv-x"))
    assert resp.status_code == 404


def test_refile_moves_to_new_project_1_to_n(isolated):
    # 1:N — a doc belongs to 0..1 investigation; re-filing moves it (not a copy).
    _seed_document(isolated, document_id="doc-3", investigation_id="inv-old")
    client = _client()
    resp = client.post("/events/typed", json=_file_event("doc-3", "inv-new"))
    assert resp.status_code == 201
    assert _doc_row(client, "doc-3")["investigation_id"] == "inv-new"
