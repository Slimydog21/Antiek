"""Hermetic tests for settings model driver tab routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_model_driver_tab_compose_routes import (
    register_settings_model_driver_tab_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_model_driver_tab_compose_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/settings/model-driver-tab/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [
                {
                    "model_id": "flash-1",
                    "tier": "flash",
                    "projected_cost_usd_high": 0.5,
                    "projected_cost_usd_low": 0.1,
                }
            ],
            "daily_cap_usd": 10,
            "spent_usd": 2,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["tab_ready"] is True
    assert body["authority"] == "settings_model_driver_tab_compose_advisory"


def test_secret_pending_400() -> None:
    r = _client().post(
        "/settings/model-driver-tab/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [{"model_id": "flash-1"}],
            "daily_cap_usd": 10,
            "spent_usd": 1,
            "pending_add_model_ids": ["sk-secretkey"],
        },
    )
    assert r.status_code == 400
    assert "secret material" in r.json()["detail"]


def test_extra_forbid() -> None:
    r = _client().post(
        "/settings/model-driver-tab/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [{"model_id": "flash-1"}],
            "daily_cap_usd": 10,
            "spent_usd": 1,
            "live_router_authorized": True,
        },
    )
    assert r.status_code == 422


def test_nd_kill_switch() -> None:
    r = _client().post(
        "/settings/model-driver-tab/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [
                {
                    "model_id": "flash-1",
                    "projected_cost_usd_high": 0.2,
                    "projected_cost_usd_low": 0.1,
                }
            ],
            "daily_cap_usd": 10,
            "spent_usd": 1,
            "nd_shadow": {
                "recommended_model_id": "other",
                "kill_switch_on": True,
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["nd_shadow_model"] is None
    assert r.json()["live_router_authorized"] is False
