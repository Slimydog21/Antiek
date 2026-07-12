"""Route tests for recursive twin + settings fullscreen MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_settings_fullscreen_mo_compose_routes import (
    register_recursive_twin_settings_fullscreen_mo_compose_routes,
)
from tests.test_settings_add_model_fullscreen_mo_draft_multi_compose_routes import (
    _payload as _sp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_settings_fullscreen_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, parent_asset_id: str = "book-1") -> dict:
    sp = _sp_payload(operator_ack=operator_ack)
    return {
        "twin": {
            "parent_asset_id": parent_asset_id,
            "source_excerpt": (
                "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
            ),
            "focus_questions": ["Where does it break?", "What residual gaps?"],
        },
        "settings_pack": {
            "settings": sp["settings"],
            "fullscreen_mo": sp["fullscreen_mo"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/recursive-twin-settings-fullscreen-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "recursive_twin_settings_fullscreen_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/recursive-twin-settings-fullscreen-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_parent_mismatch_blocks():
    c = _client()
    r = c.post(
        "/research/recursive-twin-settings-fullscreen-mo/compose",
        json=_payload(operator_ack=True, parent_asset_id="book-other"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/recursive-twin-settings-fullscreen-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
