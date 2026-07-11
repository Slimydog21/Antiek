"""Route tests for settings model inventory budget compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_model_inventory_budget_compose_routes import (
    register_settings_model_inventory_budget_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_model_inventory_budget_compose_routes(app)
    return TestClient(app)


def test_compose_inventory_budget():
    c = _client()
    r = c.post(
        "/research/settings-model-inventory-budget/compose",
        json={
            "models": [
                {"model_id": "gpt-5", "provider": "openai"},
                {"model_id": "claude-opus"},
            ],
            "pending_add_model_ids": ["mimo-pro"],
            "daily_cap_usd": 50,
            "spent_usd": 12.5,
            "selected_model_id": "gpt-5",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inventory_count"] == 2
    assert body["secrets_stored"] is False
    assert body["live_router_authorized"] is False
    assert body["bar"]["remaining_usd"] == 37.5
