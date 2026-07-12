"""Route tests for HTML-native + recursive twin MO write pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_recursive_twin_mo_write_pack_compose_routes import (
    register_html_native_recursive_twin_mo_write_pack_compose_routes,
)
from tests.test_recursive_twin_mo_price_ceiling_write_pack_compose_routes import (
    _payload as _twin_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_recursive_twin_mo_write_pack_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    tp = _twin_payload(operator_ack=operator_ack)
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
        "twin_mo": {
            "twin": tp["twin"],
            "mo_write": tp["mo_write"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/html-native-recursive-twin-mo-write-pack/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["charge_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "html_native_recursive_twin_mo_write_pack_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/html-native-recursive-twin-mo-write-pack/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["pdf_primary"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/html-native-recursive-twin-mo-write-pack/compose",
        json=payload,
    )
    assert r.status_code == 422
