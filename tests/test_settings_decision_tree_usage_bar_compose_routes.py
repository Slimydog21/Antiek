"""Route tests for settings decision tree usage bar compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_decision_tree_usage_bar_compose_routes import (
    register_settings_decision_tree_usage_bar_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_decision_tree_usage_bar_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/settings-decision-tree-usage-bar/compose",
        json={
            "selected_model_id": "gpt-5",
            "models": [
                {
                    "model_id": "gpt-5",
                    "tier": "frontier",
                    "projected_cost_usd_high": 2,
                },
                {"model_id": "composer-2.5", "projected_cost_usd_high": 0.5},
            ],
            "daily_cap_usd": 100,
            "spent_usd": 40,
            "projected_cost_usd_high": 2,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision_ready"] is True
    assert body["usage_percent"] == 40.0
    assert body["would_exceed"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["live_meter_read"] is False


def test_compose_unknown_model_400():
    c = _client()
    r = c.post(
        "/research/settings-decision-tree-usage-bar/compose",
        json={
            "selected_model_id": "nope",
            "models": [{"model_id": "gpt-5"}],
            "daily_cap_usd": 10,
            "spent_usd": 1,
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
