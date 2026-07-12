"""Route tests for settings add-model bench ND shadow compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_bench_nd_shadow_compose_routes import (
    register_settings_add_model_bench_nd_shadow_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_bench_nd_shadow_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-add-model-bench-nd-shadow/compose",
        json={
            "models": [
                {"model_id": "gpt-5.5", "provider": "openai"},
                {"model_id": "grok-4.5", "provider": "xai"},
            ],
            "pending_add_model_ids": ["mimo-v2"],
            "action": "preview",
            "week_id": "2026-W28",
            "focus_task": "deep_research",
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.9,
                },
                {
                    "event_id": "e2",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.85,
                },
                {
                    "event_id": "e3",
                    "task": "deep_research",
                    "model_id": "mimo-v2",
                    "outcome": "failed",
                    "score": 0.2,
                },
                {
                    "event_id": "e4",
                    "task": "deep_research",
                    "model_id": "mimo-v2",
                    "outcome": "failed",
                    "score": 0.3,
                },
            ],
            "decision_models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
                {"model_id": "grok-4.5", "projected_cost_usd_high": 0.3},
                {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 5,
            "projected_cost_usd_high": 0.5,
            "operator_ack": True,
            "nd_recommended_model_id": "gpt-5.5",
            "kill_switch_on": False,
            "nd_confidence": 0.7,
            "existing_tasks": ["deep_research"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["inventory_mutated"] is False
    assert body["bench_vs_nd"] == "agree"
    assert body["authority"] == (
        "settings_add_model_bench_nd_shadow_compose_advisory"
    )


def test_compose_route_kill_switch():
    c = _client()
    r = c.post(
        "/research/settings-add-model-bench-nd-shadow/compose",
        json={
            "models": [{"model_id": "gpt-5.5"}],
            "pending_add_model_ids": ["mimo-v2"],
            "action": "preview",
            "week_id": "2026-W28",
            "focus_task": "deep_research",
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.9,
                },
                {
                    "event_id": "e2",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.85,
                },
            ],
            "decision_models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
                {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 5,
            "operator_ack": True,
            "nd_recommended_model_id": "mimo-v2",
            "kill_switch_on": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bench_vs_nd"] == "nd_hidden"
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
