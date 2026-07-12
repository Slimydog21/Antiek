"""Route tests for ND shadow + Antiek-bench weekly marketplace pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.nd_shadow_antiek_bench_weekly_marketplace_compose_routes import (
    register_nd_shadow_antiek_bench_weekly_marketplace_compose_routes,
)
from tests.test_antiek_bench_weekly_marketplace_free_source_compose_routes import (
    _payload as _weekly_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_nd_shadow_antiek_bench_weekly_marketplace_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, kill_switch_on: bool = True) -> dict:
    wp = _weekly_payload(operator_ack=operator_ack)
    return {
        "nd_shadow": {
            "selected_model_id": "gpt-5",
            "nd_recommended_model_id": "claude-opus",
            "kill_switch_on": kill_switch_on,
            "confidence": 0.72,
            "task": "deep_research",
            "inventory_model_ids": ["gpt-5", "claude-opus", "mimo"],
        },
        "weekly_market": {
            "weekly_learn": wp["weekly_learn"],
            "market_research": wp["market_research"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/nd-shadow-antiek-bench-weekly-marketplace/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["purchase_executed"] is False
    assert body["hosted"] is False
    assert (
        body["authority"]
        == "nd_shadow_antiek_bench_weekly_marketplace_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/nd-shadow-antiek-bench-weekly-marketplace/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["production_router_verdict"] == "REJECT"


def test_compose_route_kill_switch_off_still_reject():
    c = _client()
    r = c.post(
        "/research/nd-shadow-antiek-bench-weekly-marketplace/compose",
        json=_payload(operator_ack=True, kill_switch_on=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nd_shadow"]["shadow_visible"] is True
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/nd-shadow-antiek-bench-weekly-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 422
