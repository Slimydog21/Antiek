"""Route tests for marketplace paid purchase gate compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_paid_purchase_gate_compose_routes import (
    register_marketplace_paid_purchase_gate_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_paid_purchase_gate_compose_routes(app)
    return TestClient(app)


def test_compose_paid():
    c = _client()
    r = c.post(
        "/research/marketplace-paid-purchase-gate/compose",
        json={
            "title": "Deep Learning Book",
            "account_id": "acct-1",
            "free_copy_available": False,
            "purchase_html_projection_sha": "sha-paid-1",
            "port_requested": True,
            "purchase_ack": True,
            "list_price_usd": 15,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 100,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["purchase_ready"] is True
    assert body["gate_ready"] is True
    assert body["purchase_executed"] is False
    assert body["charge_executed"] is False
    assert body["hosted"] is False
    assert body["pdf_view_authorized"] is False


def test_compose_budget_block():
    c = _client()
    r = c.post(
        "/research/marketplace-paid-purchase-gate/compose",
        json={
            "title": "Expensive",
            "account_id": "acct-1",
            "free_copy_available": False,
            "purchase_html_projection_sha": "sha",
            "port_requested": True,
            "purchase_ack": True,
            "list_price_usd": 50,
            "approved_spend_usd": 60,
            "remaining_budget_usd": 10,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["would_exceed_budget"] is True
    assert r.json()["purchase_ready"] is False
    assert r.json()["charge_executed"] is False
