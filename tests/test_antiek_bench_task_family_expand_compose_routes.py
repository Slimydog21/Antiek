"""Route tests for Antiek-bench task-family expand compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_task_family_expand_compose_routes import (
    register_antiek_bench_task_family_expand_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_task_family_expand_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/antiek-bench-task-family-expand/compose",
        json={
            "week_id": "2026-W28",
            "existing_tasks": ["deep_research", "twin_notes"],
            "proposed_new_tasks": [
                {
                    "task": "marketplace_port",
                    "description": "HTML book host quality",
                }
            ],
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
                {
                    "event_id": "e3",
                    "task": "deep_research",
                    "model_id": "composer",
                    "outcome": "failed",
                },
            ],
            "operator_ack": True,
            "min_events_per_task": 3,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["expand_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["suite_rewritten"] is False


def test_compose_ack_false():
    c = _client()
    r = c.post(
        "/research/antiek-bench-task-family-expand/compose",
        json={
            "week_id": "w",
            "existing_tasks": ["deep_research"],
            "proposed_new_tasks": [{"task": "chase_swarm"}],
            "events": [],
            "operator_ack": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["expand_ready"] is False
    assert r.json()["suite_rewritten"] is False
