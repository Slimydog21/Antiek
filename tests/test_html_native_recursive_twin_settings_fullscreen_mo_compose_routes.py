"""Route tests for HTML-native + recursive twin settings fullscreen MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_recursive_twin_settings_fullscreen_mo_compose_routes import (
    register_html_native_recursive_twin_settings_fullscreen_mo_compose_routes,
)
from tests.test_recursive_twin_settings_fullscreen_mo_compose_routes import (
    _payload as _tp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_recursive_twin_settings_fullscreen_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    tp = _tp_payload(operator_ack=operator_ack)
    return {
        "html_view": {
            "session_id": session_id,
            "asset_id": "book-1",
            "html_projection_sha": "sha-html-ready",
            "view_requested": True,
            "twin_bound": True,
            "twin_substrate_ready": True,
            "claimed_format": "html",
        },
        "twin_pack": {
            "twin": tp["twin"],
            "settings_pack": tp["settings_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/html-native-recursive-twin-settings-fullscreen-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["store_mutated"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "html_native_recursive_twin_settings_fullscreen_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/html-native-recursive-twin-settings-fullscreen-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["pdf_primary"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["html_view"]["session_id"] = "sess-other"
    r = c.post(
        "/research/html-native-recursive-twin-settings-fullscreen-mo/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/html-native-recursive-twin-settings-fullscreen-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
