"""LB-2 (A1c-H1 / R8): ``document_id`` on InvestigationSummary and
InvestigationStatusResponse.

The frontend's source-document affordance (``companionStore.sourceDocumentOf``,
``sourceDocumentOf.test.ts``) resolves against this field. Before LB-2 the
list DTO had no document field at all, so "open the source document" was
impossible. The field is additive and optional — null when the investigation
has no document (daemon-spawned or legacy runs). Never invented.
"""
from __future__ import annotations

import os
import tempfile

import interfaces.research.api.app as app_mod
from fastapi.testclient import TestClient
from substrate.event_log.events import log_event


def _client() -> TestClient:
    return TestClient(app_mod.create_app(register_wrestling=False))


def test_summary_carries_document_id_from_the_envelope(monkeypatch) -> None:
    tmpdir = tempfile.mkdtemp(prefix="inv-docid-")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")

    inv = "inv-docid-test"
    log_event(
        inv,
        "investigation.start_requested",
        payload={"question": "What is the spacing effect?"},
        document_id="doc-abc",
        events_dir=events,
    )
    log_event(
        inv,
        "investigation.completed",
        payload={"outcome": "done"},
        document_id="doc-abc",
        events_dir=events,
    )

    client = _client()
    resp = client.get("/investigations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next(r for r in body["investigations"] if r["investigation_id"] == inv)
    assert row["document_id"] == "doc-abc"


def test_summary_document_id_is_null_when_absent(monkeypatch) -> None:
    """Honest absent — never omitted, never ''."""
    tmpdir = tempfile.mkdtemp(prefix="inv-nodoc-")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")

    inv = "inv-nodoc-test"
    log_event(
        inv,
        "investigation.start_requested",
        payload={"question": "daemon-spawned, no document"},
        events_dir=events,
    )

    client = _client()
    resp = client.get("/investigations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next(r for r in body["investigations"] if r["investigation_id"] == inv)
    # Field present, value null — never omitted, never "".
    assert "document_id" in row
    assert row["document_id"] is None


def test_status_carries_document_id_parity_with_summary(monkeypatch) -> None:
    tmpdir = tempfile.mkdtemp(prefix="inv-status-")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")

    inv = "inv-status-test"
    log_event(
        inv,
        "investigation.start_requested",
        payload={"question": "parity"},
        document_id="doc-xyz",
        events_dir=events,
    )
    log_event(
        inv,
        "investigation.completed",
        payload={"outcome": "done"},
        events_dir=events,
    )

    client = _client()
    listed = client.get("/investigations").json()
    row = next(r for r in listed["investigations"] if r["investigation_id"] == inv)
    status = client.get(f"/investigations/{inv}").json()
    assert row["document_id"] == "doc-xyz"
    assert status["document_id"] == row["document_id"]
