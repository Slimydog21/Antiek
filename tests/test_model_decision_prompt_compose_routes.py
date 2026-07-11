"""Hermetic tests for model decision prompt compose routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_prompt_compose_routes import (
    register_model_decision_prompt_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_model_decision_prompt_compose_routes(app)
    return TestClient(app)


def test_compose_exceed() -> None:
    r = _client().post(
        "/settings/model-decision-prompt-compose/compose",
        json={
            "selected_model_id": "pro-1",
            "models": [
                {
                    "model_id": "pro-1",
                    "tier": "pro",
                    "projected_cost_usd_high": 3,
                    "projected_cost_usd_low": 1,
                }
            ],
            "daily_cap_usd": 10,
            "spent_usd": 8,
            "use_model_cost_defaults": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["would_exceed"] is True
    assert body["authority"] == "model_decision_prompt_compose_advisory"


def test_null_remaining() -> None:
    r = _client().post(
        "/settings/model-decision-prompt-compose/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [
                {
                    "model_id": "flash-1",
                    "projected_cost_usd_high": 0.5,
                }
            ],
            "daily_cap_usd": None,
            "spent_usd": None,
        },
    )
    assert r.status_code == 200
    assert r.json()["would_exceed"] is None


def test_unknown_model_400() -> None:
    r = _client().post(
        "/settings/model-decision-prompt-compose/compose",
        json={
            "selected_model_id": "nope",
            "models": [{"model_id": "flash-1"}],
            "daily_cap_usd": 10,
            "spent_usd": 1,
        },
    )
    assert r.status_code == 400


def test_extra_forbid() -> None:
    r = _client().post(
        "/settings/model-decision-prompt-compose/compose",
        json={
            "selected_model_id": "flash-1",
            "models": [{"model_id": "flash-1"}],
            "daily_cap_usd": 10,
            "spent_usd": 1,
            "would_exceed": False,
        },
    )
    assert r.status_code == 422
