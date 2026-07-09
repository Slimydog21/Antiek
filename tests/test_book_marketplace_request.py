from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_purchase_request_requires_manual_no_spend_ack() -> None:
    client = _client()

    resp = client.post(
        "/books/marketplace/purchase-request",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "max_price_usd_cents": 2_500,
            "acknowledge_manual_purchase_only": False,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "manual_purchase_ack_required"


def test_purchase_request_is_precheckout_no_external_action_contract() -> None:
    client = _client()

    resp = client.post(
        "/books/marketplace/purchase-request",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "source_url": "https://example.com/book",
            "store": "publisher",
            "max_price_usd_cents": 2_500,
            "desired_format": "epub",
            "acknowledge_manual_purchase_only": True,
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["request_id"].startswith("bookreq-")
    assert body["status"] == "needs_operator_purchase"
    assert body["title"] == "The Dream Machine"
    assert body["import_target"] == "antiek_html"
    assert body["purchase_allowed"] is False
    assert body["external_call_performed"] is False
    assert body["spend_reserved_usd_cents"] == 0
    assert body["charge_attempted"] is False
    assert body["ingest_attempted"] is False
    assert body["html_hosting_required"] is True
    assert any("No checkout" in note for note in body["policy_notes"])


def test_html_import_preflight_requires_ack_and_legal_access() -> None:
    client = _client()

    missing_ack = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "has_legal_access": True,
            "acknowledge_no_upload_or_ingest": False,
        },
    )
    assert missing_ack.status_code == 400
    assert missing_ack.json()["detail"] == "html_import_preflight_ack_required"

    missing_rights = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "has_legal_access": False,
            "acknowledge_no_upload_or_ingest": True,
        },
    )
    assert missing_rights.status_code == 400
    assert missing_rights.json()["detail"] == "legal_access_required"


def test_html_import_preflight_is_no_upload_no_ingest_contract() -> None:
    client = _client()

    resp = client.post(
        "/books/import/html-preflight",
        json={
            "title": "The Dream Machine",
            "author": "M. Mitchell Waldrop",
            "source_request_id": "bookreq-safe123",
            "file_name": "dream-machine.epub",
            "file_format": "epub",
            "has_legal_access": True,
            "acknowledge_no_upload_or_ingest": True,
        },
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["import_preflight_id"].startswith("bookimp-")
    assert body["status"] == "ready_for_operator_file"
    assert body["source_request_id"] == "bookreq-safe123"
    assert body["import_target"] == "antiek_html"
    assert body["external_call_performed"] is False
    assert body["file_uploaded"] is False
    assert body["file_read_attempted"] is False
    assert body["ingest_attempted"] is False
    assert body["graph_mutation_performed"] is False
    assert body["html_conversion_required"] is True
    assert body["html_hosting_required"] is True
    assert any("No upload" in note for note in body["policy_notes"])
