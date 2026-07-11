"""Route tests for competition DR quality + source pack compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    register_competition_dr_quality_source_pack_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_dr_quality_source_pack_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/competition-dr-quality-source-pack/compose",
        json={
            "session_id": "sess-1",
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
    assert body["pack_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False


def test_compose_no_behind_blocks():
    c = _client()
    r = c.post(
        "/research/competition-dr-quality-source-pack/compose",
        json={
            "session_id": "sess-1",
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
                {
                    "citation_id": "c1",
                    "family": "arxiv",
                    "title": "T",
                }
            ],
            "quality_overall": 0.9,
            "would_exceed": False,
            "operator_ack": True,
            "require_no_behind_gaps": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatch_authorized"] is False
