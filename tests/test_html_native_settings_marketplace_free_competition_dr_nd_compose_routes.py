"""Route tests for HTML-native view over settings marketplace free competition pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_settings_marketplace_free_competition_dr_nd_compose_routes import (
    register_html_native_settings_marketplace_free_competition_dr_nd_compose_routes,
)
from tests.test_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    HTML_VIEW,
    SETTINGS_PACK,
)

_PATH = "/research/html-native-settings-marketplace-free-competition-dr-nd/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_settings_marketplace_free_competition_dr_nd_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "html_view": HTML_VIEW,
        "settings_pack": SETTINGS_PACK,
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
    assert body["html_view"]["pack_ready"] is True
    assert body["settings_pack"]["pack_ready"] is True
    assert body["pdf_primary"] is False
    assert body["pdf_view_authorized"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["live_router_authorized"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["pdf_primary"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_session_mismatch():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["html_view"] = {**HTML_VIEW, "session_id": "sess-other"}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
