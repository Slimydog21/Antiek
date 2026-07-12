"""Route tests for HTML-native view over marketplace free settings ND twin pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_marketplace_free_settings_nd_twin_compose_routes import (
    register_html_native_marketplace_free_settings_nd_twin_compose_routes,
)
from tests.test_marketplace_free_settings_add_model_nd_shadow_twin_compose import (
    MARKET,
    SETTINGS_PACK,
)

_PATH = "/research/html-native-marketplace-free-settings-nd-twin/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_marketplace_free_settings_nd_twin_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "html_view": {
            "session_id": "sess-1",
            "asset_id": "book-1",
            "html_projection_sha": "sha-html-ready",
            "view_requested": True,
            "twin_bound": True,
            "twin_substrate_ready": True,
            "claimed_format": "html",
        },
        "market_pack": {
            "market": MARKET,
            "settings_pack": SETTINGS_PACK,
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["pdf_primary"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "html_native_marketplace_free_settings_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["pdf_primary"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
