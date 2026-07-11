"""Route tests for marketplace HTML twin interrogation compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.marketplace_html_twin_interrogation_compose_routes import (
    register_marketplace_html_twin_interrogation_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_marketplace_html_twin_interrogation_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/marketplace-html-twin-interrogation/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "book-1",
            "title": "Scaling Laws",
            "account_id": "acct-1",
            "free_copy_available": True,
            "free_html_projection_sha": "sha-free",
            "port_requested": True,
            "purchase_ack": False,
            "list_price_usd": 10,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 50,
            "operator_ack": True,
            "view_requested": True,
            "include_twin_feed": True,
            "include_interrogation": True,
            "questions": [
                {
                    "question_id": "q1",
                    "body": "Core thesis?",
                    "priority": 2,
                },
                {
                    "question_id": "q2",
                    "body": "Counter-evidence?",
                    "priority": 1,
                },
            ],
            "chase_mode": "swarm_fanout",
            "models": [
                {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
            ],
            "selected_model_id": "gpt-5.5",
            "daily_cap_usd": 25,
            "spent_usd": 2,
            "projected_cost_usd_high": 0.4,
            "would_exceed": False,
            "source_families": ["arxiv"],
            "user_prompt": "Interrogate book",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["purchase_executed"] is False
    assert body["pdf_view_authorized"] is False
    assert body["live_dispatched"] is False
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
