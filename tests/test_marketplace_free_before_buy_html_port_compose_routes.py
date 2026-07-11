"""Route tests for marketplace free-before-buy HTML port compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_before_buy_html_port_compose_routes import (
    register_marketplace_free_before_buy_html_port_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_before_buy_html_port_compose_routes(app)
    return TestClient(app)


def test_compose_free_port():
    c = _client()
    r = c.post(
        "/research/marketplace-free-before-buy-port/compose",
        json={
            "title": "Deep Learning",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-1",
            "purchase_ack": False,
            "port_requested": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "prefer_free_html"
    assert body["port_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["pdf_view_authorized"] is False
