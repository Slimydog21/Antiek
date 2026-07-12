"""Route tests for Antiek-bench weekly + marketplace free source pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_weekly_marketplace_free_source_compose_routes import (
    register_antiek_bench_weekly_marketplace_free_source_compose_routes,
)
from tests.test_marketplace_free_source_attach_record_prompt_compose_routes import (
    _payload as _market_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_weekly_marketplace_free_source_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    mp = _market_payload(operator_ack=operator_ack)
    return {
        "weekly_learn": {
            "week_id": "2026-W28",
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
                {
                    "event_id": "e3",
                    "task": "twin_notes",
                    "model_id": "claude",
                    "outcome": "worked",
                },
                {
                    "event_id": "e4",
                    "task": "twin_notes",
                    "model_id": "claude",
                    "outcome": "worked",
                },
            ],
        },
        "market_research": {
            "market": mp["market"],
            "research": mp["research"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/antiek-bench-weekly-marketplace-free-source/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["week_id"] == "2026-W28"
    assert (
        body["authority"]
        == "antiek_bench_weekly_marketplace_free_source_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/antiek-bench-weekly-marketplace-free-source/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["store_mutated"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/antiek-bench-weekly-marketplace-free-source/compose",
        json=payload,
    )
    assert r.status_code == 422
