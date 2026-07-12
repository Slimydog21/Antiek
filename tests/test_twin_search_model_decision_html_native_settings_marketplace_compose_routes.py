"""Route tests for twin search over model decision HTML-native settings marketplace pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_search_model_decision_html_native_settings_marketplace_compose_routes import (
    register_twin_search_model_decision_html_native_settings_marketplace_compose_routes,
)
from tests.test_twin_search_model_decision_html_native_settings_marketplace_compose import (
    MODEL_DECISION_PACK,
    TWIN_RECORDS,
)

_PATH = (
    "/research/twin-search-model-decision-html-native-settings-marketplace/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_search_model_decision_html_native_settings_marketplace_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "search_query": "scaling noise",
        "twin_records": TWIN_RECORDS,
        "model_decision_pack": MODEL_DECISION_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["hit_count"] >= 1
    assert body["model_decision_pack"]["pack_ready"] is True
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert body["secrets_stored"] is False
    assert body["live_router_authorized"] is False
    assert body["live_meter_read"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "twin_search_model_decision_html_native_settings_marketplace_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False


def test_compose_route_zero_hits():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["search_query"] = "zzzznonexistenttoken"
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hit_count"] == 0
    assert body["pack_ready"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
