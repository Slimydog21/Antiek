"""Route tests for NotDiamond shadow advisory compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.notdiamond_shadow_advisory_compose_routes import (
    register_notdiamond_shadow_advisory_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_notdiamond_shadow_advisory_compose_routes(app)
    return TestClient(app)


def test_compose_kill_on_reject():
    c = _client()
    r = c.post(
        "/research/notdiamond-shadow/compose",
        json={
            "selected_model_id": "gpt-5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": True,
            "inventory_model_ids": ["gpt-5", "claude-opus"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["shadow_visible"] is False


def test_compose_shadow_differs():
    c = _client()
    r = c.post(
        "/research/notdiamond-shadow/compose",
        json={
            "selected_model_id": "gpt-5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": False,
            "confidence": 0.7,
            "inventory_model_ids": ["gpt-5", "claude-opus"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["shadow_visible"] is True
    assert body["differs_from_selected"] is True
    assert body["suggested_model_id"] == "claude-opus"
    assert body["live_router_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
