"""Route tests for competition DR + ND shadow weekly marketplace pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_dr_nd_shadow_weekly_marketplace_compose_routes import (
    register_competition_dr_nd_shadow_weekly_marketplace_compose_routes,
)
from tests.test_nd_shadow_antiek_bench_weekly_marketplace_compose_routes import (
    _payload as _nd_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_dr_nd_shadow_weekly_marketplace_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, would_exceed: bool = False) -> dict:
    np = _nd_payload(operator_ack=operator_ack)
    return {
        "competition": {
            "session_id": "sess-1",
            "competitor_decisions": [
                {
                    "competitor": "Perplexity",
                    "area": "citation_grounding",
                    "decision_summary": "Inline citations with source cards",
                    "antiek_status": "parity",
                },
                {
                    "competitor": "OpenAI DR",
                    "area": "multi_agent_orchestration",
                    "decision_summary": "Planner + browser agents",
                    "antiek_status": "behind",
                    "residual": "strengthen collective floating cohesive pack",
                },
            ],
            "requested_families": ["arxiv", "substack"],
            "citations": [
                {
                    "citation_id": "c1",
                    "family": "arxiv",
                    "title": "Scaling Laws under Noise",
                    "external_id": "arxiv:2301.00001",
                },
                {
                    "citation_id": "c2",
                    "family": "substack",
                    "title": "Research notes on evals",
                    "url": "https://example.substack.com/p/evals",
                },
            ],
            "quality_overall": 0.8,
            "quality_floor": 0.5,
            "would_exceed": would_exceed,
        },
        "nd_weekly": {
            "nd_shadow": np["nd_shadow"],
            "weekly_market": np["weekly_market"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/competition-dr-nd-shadow-weekly-marketplace/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert body["purchase_executed"] is False
    assert (
        body["authority"]
        == "competition_dr_nd_shadow_weekly_marketplace_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/competition-dr-nd-shadow-weekly-marketplace/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False


def test_compose_route_would_exceed_blocks():
    c = _client()
    r = c.post(
        "/research/competition-dr-nd-shadow-weekly-marketplace/compose",
        json=_payload(operator_ack=True, would_exceed=True),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/competition-dr-nd-shadow-weekly-marketplace/compose",
        json=payload,
    )
    assert r.status_code == 422
