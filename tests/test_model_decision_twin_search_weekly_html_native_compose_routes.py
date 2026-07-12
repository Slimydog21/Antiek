"""Route tests for model decision + twin search weekly HTML-native pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_twin_search_weekly_html_native_compose_routes import (
    register_model_decision_twin_search_weekly_html_native_compose_routes,
)
from tests.test_twin_search_antiek_bench_weekly_html_native_compose_routes import (
    _payload as _tsp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_model_decision_twin_search_weekly_html_native_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    tsp = _tsp_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "decision": {
            "selected_model_id": "gpt-5.5",
            "models": [
                {
                    "model_id": "gpt-5.5",
                    "projected_cost_usd_high": 2,
                    "projected_cost_usd_low": 1,
                }
            ],
            "daily_cap_usd": 50,
            "spent_usd": 10,
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
            "focus_task": "deep_research",
        },
        "twin_search_pack": {
            "search_query": tsp["search_query"],
            "twin_records": tsp["twin_records"],
            "weekly_html": tsp["weekly_html"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/model-decision-twin-search-weekly-html-native/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["live_meter_read"] is False
    assert body["remote_index_queried"] is False
    assert body["suite_rewritten"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "model_decision_twin_search_weekly_html_native_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/model-decision-twin-search-weekly-html-native/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_router_authorized"] is False


def test_compose_route_budget_exceed_blocks():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["decision"]["spent_usd"] = 49
    payload["decision"]["projected_cost_usd_high"] = 5
    payload["decision"]["models"] = [
        {"model_id": "gpt-5.5", "projected_cost_usd_high": 5}
    ]
    r = c.post(
        "/research/model-decision-twin-search-weekly-html-native/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"]["would_exceed"] is True
    assert body["pack_ready"] is False
    assert body["suite_rewritten"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/model-decision-twin-search-weekly-html-native/compose",
        json=payload,
    )
    assert r.status_code == 422
