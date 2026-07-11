"""Route tests for paid purchase HTML view session compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.paid_purchase_html_view_session_compose_routes import (
    register_paid_purchase_html_view_session_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_paid_purchase_html_view_session_compose_routes(app)
    return TestClient(app)


def test_compose_paid():
    c = _client()
    r = c.post(
        "/research/paid-purchase-html-view-session/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "book-1",
            "title": "Deep Learning",
            "account_id": "acct-1",
            "free_copy_available": False,
            "purchase_html_projection_sha": "sha-paid",
            "port_requested": True,
            "purchase_ack": True,
            "list_price_usd": 15,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 100,
            "operator_ack": True,
            "view_requested": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_package_ready"] is True
    assert body["charge_executed"] is False
    assert body["pdf_view_authorized"] is False
    assert body["hosted"] is False


def test_compose_free():
    c = _client()
    r = c.post(
        "/research/paid-purchase-html-view-session/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "book-1",
            "title": "Scaling",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free",
            "port_requested": True,
            "purchase_ack": False,
            "list_price_usd": 10,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 50,
            "operator_ack": True,
            "view_requested": True,
            "twin_bound": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["session_package_ready"] is True
    assert r.json()["purchase_executed"] is False
