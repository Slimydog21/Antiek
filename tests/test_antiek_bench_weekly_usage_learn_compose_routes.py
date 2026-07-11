"""Route tests for Antiek-bench weekly usage-learn compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_weekly_usage_learn_compose_routes import (
    register_antiek_bench_weekly_usage_learn_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_weekly_usage_learn_compose_routes(app)
    return TestClient(app)


def test_compose_learn():
    c = _client()
    r = c.post(
        "/research/antiek-bench-weekly-learn/compose",
        json={
            "week_id": "2026-W28",
            "operator_ack": True,
            "min_events_per_task": 2,
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5",
                    "outcome": "failed",
                },
                {
                    "event_id": "e2",
                    "task": "deep_research",
                    "model_id": "gpt-5",
                    "outcome": "failed",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["learn_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["proposal_count"] == 1
