"""Route tests for model decision + twin search HTML-native marketplace pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_twin_search_html_native_marketplace_compose_routes import (
    register_model_decision_twin_search_html_native_marketplace_compose_routes,
)
from tests.test_twin_search_html_native_recursive_twin_marketplace_compose_routes import (
    _payload as _twin_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_model_decision_twin_search_html_native_marketplace_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    tp = _twin_payload(operator_ack=operator_ack)
    return {
        "decision": {
            "selected_model_id": "gpt-5.5",
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                    "projected_cost_usd_low": 1,
                },
                {
                    "model_id": "composer-2.5",
                    "tier": "workhorse",
                    "projected_cost_usd_high": 0.5,
                },
            ],
            "daily_cap_usd": 50,
            "spent_usd": 10,
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
            "focus_task": "deep_research",
            "pending_add_model_ids": ["mimo-v2"],
        },
        "twin_search_pack": {
            "search_query": tp["search_query"],
            "twin_records": tp["twin_records"],
            "html_pack": tp["html_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/model-decision-twin-search-html-native-marketplace/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["decision"]["decision_ready"] is True
    assert body["decision"]["would_exceed"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["purchase_executed"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "model_decision_twin_search_html_native_marketplace_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/model-decision-twin-search-html-native-marketplace/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False


def test_compose_route_would_exceed():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["decision"]["projected_cost_usd_high"] = 100
    payload["decision"]["daily_cap_usd"] = 50
    payload["decision"]["spent_usd"] = 10
    r = c.post(
        "/research/model-decision-twin-search-html-native-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"]["would_exceed"] is True
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/model-decision-twin-search-html-native-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 422
