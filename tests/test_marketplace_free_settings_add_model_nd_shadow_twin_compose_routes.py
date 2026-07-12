"""Route tests for marketplace free over settings ND twin presentation pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_free_settings_add_model_nd_shadow_twin_compose_routes import (
    register_marketplace_free_settings_add_model_nd_shadow_twin_compose_routes,
)
from tests.test_settings_add_model_nd_shadow_twin_presentation_compose import (
    ND_PACK,
    SETTINGS,
)

_PATH = "/research/marketplace-free-settings-add-model-nd-shadow-twin/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_free_settings_add_model_nd_shadow_twin_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "market": {
            "title": "Scaling Laws Book",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free-html",
            "purchase_ack": False,
            "port_requested": True,
        },
        "settings_pack": {
            "settings": SETTINGS,
            "nd_pack": ND_PACK,
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "marketplace_free_settings_add_model_nd_shadow_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["purchase_executed"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
