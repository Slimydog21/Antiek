"""Cross-graph citation endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def _client():
    return TestClient(create_app(register_wrestling=False))


def test_post_citation_returns_reference_id():
    client = _client()
    resp = client.post(
        "/cross-graph/citations",
        json={
            "referencing_user_id": "user-B",
            "referencing_investigation_id": "inv-1",
            "referenced_user_id": "user-A",
            "referenced_note_id": "note-7",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reference_id"].startswith("xref-")
    assert body["referenced_user_id"] == "user-A"
    assert body["federated_substrate_id"] is None  # same-substrate citation


def test_post_citation_federation_records_partner_id():
    client = _client()
    resp = client.post(
        "/cross-graph/citations",
        json={
            "referencing_user_id": "user-B",
            "referencing_investigation_id": "inv-2",
            "referenced_user_id": "user-Z",
            "referenced_note_id": "note-99",
            "federated_substrate_id": "partner-research-coop",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["federated_substrate_id"] == "partner-research-coop"
