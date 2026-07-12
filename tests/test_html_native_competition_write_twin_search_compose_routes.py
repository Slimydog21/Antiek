"""Route tests for HTML-native competition write twin search compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_competition_write_twin_search_compose_routes import (
    register_html_native_competition_write_twin_search_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_competition_write_twin_search_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/html-native-competition-write-twin-search/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "asset-1",
            "html_projection_sha": "sha-html-1",
            "view_requested": True,
            "twin_bound": True,
            "twin_substrate_ready": True,
            "claimed_format": "html",
            "operator_ack": True,
            "competition": {
                "draft_id": "draft-1",
                "parent_asset_id": "asset-1",
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
                "would_exceed": False,
                "search_query": "scaling orchestration citations",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["remote_index_queried"] is False
    assert body["twin_written"] is False
    assert (
        body["authority"]
        == "html_native_competition_write_twin_search_compose_advisory"
    )


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/html-native-competition-write-twin-search/compose",
        json={
            "session_id": "sess-2",
            "asset_id": "asset-1",
            "html_projection_sha": "sha-html-1",
            "view_requested": True,
            "twin_bound": True,
            "claimed_format": "html",
            "operator_ack": True,
            "competition": {
                "draft_id": "draft-2",
                "parent_asset_id": "asset-1",
                "competitor_decisions": [
                    {
                        "competitor": "Perplexity",
                        "area": "citation_grounding",
                        "decision_summary": "Inline citations",
                        "antiek_status": "parity",
                    }
                ],
                "requested_families": ["arxiv"],
                "citations": [
                    {
                        "citation_id": "c1",
                        "family": "arxiv",
                        "title": "Paper",
                        "external_id": "arxiv:1",
                    }
                ],
                "quality_overall": 0.9,
                "would_exceed": True,
                "search_query": "paper",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["pdf_view_authorized"] is False
