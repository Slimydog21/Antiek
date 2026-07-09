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
