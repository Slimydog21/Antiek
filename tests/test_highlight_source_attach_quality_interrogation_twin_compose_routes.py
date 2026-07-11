"""Route tests for highlight source attach quality interrogation twin."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.highlight_source_attach_quality_interrogation_twin_compose_routes import (
    register_highlight_source_attach_quality_interrogation_twin_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_highlight_source_attach_quality_interrogation_twin_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/highlight-source-attach-quality-interrogation-twin/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "power-law scaling",
            "gated": False,
            "would_exceed": False,
            "selected_model_id": "gpt-5.5",
            "operator_ack": True,
            "session_id": "sess-1",
            "requested_families": ["arxiv"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Scaling Laws for Neural Language Models",
                    "html_fragment": "<article>abstract…</article>",
                }
            ],
            "quality_overall": 0.9,
            "questions": [
                {
                    "question_id": "q1",
                    "body": "How does this highlight relate?",
                    "priority": 2,
                }
            ],
            "chase_mode": "single_question",
            "models": [{"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4}],
            "daily_cap_usd": 20,
            "spent_usd": 1,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["twin_written"] is False
    assert body["twin_feed"]["finding_count"] == 3
    assert body["authority"] == (
        "highlight_source_attach_quality_interrogation_twin_compose_advisory"
    )


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/highlight-source-attach-quality-interrogation-twin/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "claim",
            "gated": False,
            "would_exceed": True,
            "operator_ack": True,
            "session_id": "s",
            "requested_families": ["arxiv"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Paper",
                    "html_fragment": "<p>x</p>",
                }
            ],
            "quality_overall": 0.9,
            "questions": [
                {"question_id": "q1", "body": "Q?", "priority": 1}
            ],
            "chase_mode": "single_question",
            "models": [{"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5}],
            "daily_cap_usd": 1,
            "spent_usd": 0.9,
            "projected_cost_usd_high": 0.5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
