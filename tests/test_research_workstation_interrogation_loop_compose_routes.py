"""Route tests for research workstation interrogation loop."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_workstation_interrogation_loop_compose_routes import (
    register_research_workstation_interrogation_loop_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_workstation_interrogation_loop_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/workstation-interrogation-loop/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "questions": [
                {
                    "question_id": "q1",
                    "body": "What is the core claim?",
                    "priority": 2,
                },
                {
                    "question_id": "q2",
                    "body": "Counter-evidence?",
                    "priority": 1,
                },
            ],
            "chase_mode": "swarm_fanout",
            "user_prompt": "Interrogate and chase",
            "selected_model_id": "gpt-5.5",
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
            ],
            "daily_cap_usd": 20,
            "spent_usd": 2,
            "projected_cost_usd_high": 0.4,
            "would_exceed": False,
            "source_families": ["arxiv"],
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["loop_ready"] is True
    assert body["live_dispatched"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_router_authorized"] is False
