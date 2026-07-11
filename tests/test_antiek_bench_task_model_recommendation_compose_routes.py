"""Route tests for Antiek-bench task model recommendation."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_task_model_recommendation_compose_routes import (
    register_antiek_bench_task_model_recommendation_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_task_model_recommendation_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/antiek-bench-task-model-recommendation/compose",
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
                    "score": 0.88,
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
                    "score": 0.25,
                },
            ],
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
                {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 5,
            "projected_cost_usd_high": 0.5,
            "operator_ack": True,
            "existing_tasks": ["deep_research"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation"]["recommended_model_id"] == "gpt-5.5"
    assert body["live_router_authorized"] is False
    assert body["suite_rewritten"] is False
    assert body["pack_ready"] is True
