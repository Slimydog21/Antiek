"""Route tests for model decision + twin search HTML-native ND twin pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_twin_search_html_native_nd_twin_compose_routes import (
    register_model_decision_twin_search_html_native_nd_twin_compose_routes,
)
from tests.test_model_decision_twin_search_html_native_nd_twin_compose import (
    DECISION,
    TWIN_SEARCH_PACK,
)

_PATH = "/research/model-decision-twin-search-html-native-nd-twin/compose"


def _client() -> TestClient:
    app = FastAPI()
    register_model_decision_twin_search_html_native_nd_twin_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "decision": DECISION,
        "twin_search_pack": TWIN_SEARCH_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "model_decision_twin_search_html_native_nd_twin_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
