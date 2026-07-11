"""Route tests for competition quality + interrogation loop."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_quality_interrogation_loop_compose_routes import (
    register_competition_quality_interrogation_loop_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_quality_interrogation_loop_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/competition-quality-interrogation-loop/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "competitor_decisions": [
                {
                    "competitor": "Perplexity",
                    "area": "citation_grounding",
                    "decision_summary": "Inline citations",
                    "antiek_status": "parity",
                }
            ],
            "requested_families": ["arxiv", "substack"],
            "citations": [
                {
                    "citation_id": "c1",
                    "family": "arxiv",
                    "title": "Paper",
                    "external_id": "arxiv:2001.08361",
                },
                {
                    "citation_id": "c2",
                    "family": "substack",
                    "title": "Essay",
                },
            ],
            "quality_overall": 0.85,
            "quality_floor": 0.7,
            "would_exceed": False,
            "questions": [
                {
                    "question_id": "q1",
                    "body": "Core claim?",
                    "priority": 2,
                },
                {
                    "question_id": "q2",
                    "body": "Counter-evidence?",
                    "priority": 1,
                },
            ],
            "chase_mode": "swarm_fanout",
            "user_prompt": "Chase gaps",
            "selected_model_id": "gpt-5.5",
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
            ],
            "daily_cap_usd": 30,
            "spent_usd": 3,
            "projected_cost_usd_high": 0.4,
            "source_families": ["arxiv"],
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
