"""Route tests for model decision + HTML-native competition compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_html_native_competition_compose_routes import (
    register_model_decision_html_native_competition_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_model_decision_html_native_competition_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/model-decision-html-native-competition/compose",
        json={
            "decision": {
                "selected_model_id": "gpt-5.5",
                "models": [
                    {
                        "model_id": "gpt-5.5",
                        "tier": "frontier",
                        "projected_cost_usd_high": 2,
                        "projected_cost_usd_low": 1,
                    }
                ],
                "daily_cap_usd": 50,
                "spent_usd": 10,
            },
            "competition_view": {
                "session_id": "sess-1",
                "asset_id": "asset-1",
                "html_projection_sha": "sha-html-1",
                "view_requested": True,
                "twin_bound": True,
                "twin_substrate_ready": True,
                "claimed_format": "html",
                "competition": {
                    "draft_id": "draft-1",
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
                            "title": "Scaling Laws under Noise",
                            "external_id": "arxiv:2301.00001",
                        }
                    ],
                    "quality_overall": 0.8,
                    "would_exceed": False,
                    "search_query": "scaling",
                },
            },
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["pdf_view_authorized"] is False
    assert body["remote_index_queried"] is False
    assert (
        body["authority"]
        == "model_decision_html_native_competition_compose_advisory"
    )


def test_compose_route_budget_block():
    c = _client()
    r = c.post(
        "/research/model-decision-html-native-competition/compose",
        json={
            "decision": {
                "selected_model_id": "gpt-5.5",
                "models": [
                    {
                        "model_id": "gpt-5.5",
                        "projected_cost_usd_high": 5,
                        "projected_cost_usd_low": 4,
                    }
                ],
                "daily_cap_usd": 50,
                "spent_usd": 49,
            },
            "competition_view": {
                "session_id": "sess-2",
                "asset_id": "asset-1",
                "html_projection_sha": "sha-html-1",
                "view_requested": True,
                "twin_bound": True,
                "claimed_format": "html",
                "competition": {
                    "draft_id": "draft-2",
                    "parent_asset_id": "asset-1",
                    "competitor_decisions": [
                        {
                            "competitor": "Perplexity",
                            "area": "citation_grounding",
                            "decision_summary": "Inline",
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
                    "would_exceed": False,
                    "search_query": "paper",
                },
            },
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
