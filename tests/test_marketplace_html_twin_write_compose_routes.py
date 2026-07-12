"""Route tests for marketplace HTML twin write compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_html_twin_write_compose_routes import (
    register_marketplace_html_twin_write_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_html_twin_write_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/marketplace-html-twin-write/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "book-1",
            "draft_id": "draft-1",
            "title": "Scaling Laws",
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
            "twin_findings": [
                {
                    "source_id": "q1",
                    "body": "What is the core thesis?",
                    "kind": "question",
                },
                {
                    "source_id": "i1",
                    "body": "Power-law scaling insight",
                    "kind": "insight",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["charge_executed"] is False
    assert body["pdf_view_authorized"] is False
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["authority"] == "marketplace_html_twin_write_compose_advisory"


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/marketplace-html-twin-write/compose",
        json={
            "session_id": "s",
            "asset_id": "b",
            "draft_id": "d",
            "title": "Expensive",
            "account_id": "a",
            "free_copy_available": False,
            "purchase_html_projection_sha": "sha",
            "port_requested": True,
            "purchase_ack": True,
            "list_price_usd": 50,
            "approved_spend_usd": 60,
            "remaining_budget_usd": 5,
            "operator_ack": True,
            "view_requested": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["charge_executed"] is False
