"""Route tests for NotDiamond + bench decision shadow."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.notdiamond_bench_decision_shadow_compose_routes import (
    register_notdiamond_bench_decision_shadow_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_notdiamond_bench_decision_shadow_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/notdiamond-bench-decision-shadow/compose",
        json={
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
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
                {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 4,
            "nd_recommended_model_id": "gpt-5.5",
            "kill_switch_on": False,
            "operator_ack": True,
            "projected_cost_usd_high": 0.5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["pack_ready"] is True
    assert body["bench_vs_nd"] == "agree"
