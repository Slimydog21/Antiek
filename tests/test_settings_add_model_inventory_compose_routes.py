"""Route tests for settings add-model inventory compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_inventory_compose_routes import (
    register_settings_add_model_inventory_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_inventory_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-add-model-inventory/compose",
        json={
            "models": [{"model_id": "gpt-5.5", "provider": "openai"}],
            "pending_add_model_ids": ["mimo-v2"],
            "action": "propose_add",
            "daily_cap_usd": 20,
            "spent_usd": 2,
            "operator_ack": True,
            "selected_model_id": "gpt-5.5",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["proposed_new_count"] == 1
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["live_router_authorized"] is False
