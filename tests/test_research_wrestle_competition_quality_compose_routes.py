"""Route tests for research wrestle + competition quality compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_wrestle_competition_quality_compose_routes import (
    register_research_wrestle_competition_quality_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_wrestle_competition_quality_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/wrestle-competition-quality/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "floating_instance_count": 2,
            "completed_floating_count": 1,
            "twin_insight_count": 3,
            "twin_question_count": 2,
            "open_question_count": 1,
            "preferred_view_mode": "floating",
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
                    "title": "Scaling Laws",
                    "external_id": "arxiv:2301.00001",
                },
                {
                    "citation_id": "c2",
                    "family": "substack",
                    "title": "Evals",
                    "url": "https://example.substack.com/p/evals",
                },
            ],
            "quality_overall": 0.8,
            "quality_floor": 0.5,
            "would_exceed": False,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False


def test_compose_no_behind_blocks():
    c = _client()
    r = c.post(
        "/research/wrestle-competition-quality/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "floating_instance_count": 2,
            "completed_floating_count": 1,
            "twin_insight_count": 2,
            "twin_question_count": 1,
            "open_question_count": 1,
            "competitor_decisions": [
                {
                    "competitor": "OpenAI DR",
                    "area": "multi_agent_orchestration",
                    "decision_summary": "Planner agents",
                    "antiek_status": "behind",
                    "residual": "cohesive pack",
                }
            ],
            "requested_families": ["arxiv"],
            "citations": [
                {"citation_id": "c1", "family": "arxiv", "title": "T"}
            ],
            "quality_overall": 0.9,
            "would_exceed": False,
            "operator_ack": True,
            "require_no_behind_gaps": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["session_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False
