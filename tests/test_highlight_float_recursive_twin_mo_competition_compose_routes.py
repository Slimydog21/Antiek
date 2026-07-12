"""Route tests for highlight float → recursive twin MO competition."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.highlight_float_recursive_twin_mo_competition_compose_routes import (
    register_highlight_float_recursive_twin_mo_competition_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_highlight_float_recursive_twin_mo_competition_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/highlight-float-recursive-twin-mo-competition/compose",
        json={
            "highlight_surface": {
                "session_id": "sess-1",
                "parent_asset_id": "book-1",
                "highlight": "scaling laws under noise",
                "gated": False,
                "would_exceed": False,
                "surface_action": "spawn_only",
                "source_families": ["arxiv"],
            },
            "mo_competition": {
                "mo": {
                    "operator_id": "op-1",
                    "work_minutes": 120,
                    "goals": [
                        {"goal_id": "g1", "title": "Survey arxiv"},
                        {"goal_id": "g2", "title": "Draft notes"},
                    ],
                    "usd_per_hour": 15,
                    "approved_ceiling_usd": 40,
                    "unattended_ack": True,
                    "spend_consent": True,
                },
                "research": {
                    "decision": {
                        "selected_model_id": "gpt-5.5",
                        "models": [
                            {
                                "model_id": "gpt-5.5",
                                "projected_cost_usd_high": 2,
                                "projected_cost_usd_low": 1,
                            }
                        ],
                        "daily_cap_usd": 50,
                        "spent_usd": 10,
                    },
                    "competition_view": {
                        "session_id": "sess-1",
                        "asset_id": "book-1",
                        "html_projection_sha": "sha-html-1",
                        "view_requested": True,
                        "twin_bound": True,
                        "claimed_format": "html",
                        "competition": {
                            "draft_id": "draft-1",
                            "parent_asset_id": "book-1",
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
                                    "title": "Scaling Laws under Noise",
                                    "external_id": "arxiv:2301.00001",
                                }
                            ],
                            "quality_overall": 0.8,
                            "would_exceed": False,
                            "search_query": "scaling",
                        },
                    },
                },
            },
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["twin_written"] is False
    assert body["live_execution_authorized"] is False
    assert (
        body["authority"]
        == "highlight_float_recursive_twin_mo_competition_compose_advisory"
    )


def test_compose_route_gated():
    c = _client()
    r = c.post(
        "/research/highlight-float-recursive-twin-mo-competition/compose",
        json={
            "highlight_surface": {
                "session_id": "s",
                "parent_asset_id": "b",
                "highlight": "secret",
                "gated": True,
                "would_exceed": False,
                "surface_action": "spawn_only",
            },
            "mo_competition": {
                "mo": {
                    "operator_id": "op-1",
                    "work_minutes": 60,
                    "goals": [{"goal_id": "g1", "title": "T"}],
                    "usd_per_hour": 10,
                    "approved_ceiling_usd": 20,
                    "unattended_ack": True,
                    "spend_consent": True,
                },
                "research": {
                    "decision": {
                        "selected_model_id": "gpt-5.5",
                        "models": [{"model_id": "gpt-5.5"}],
                        "daily_cap_usd": 50,
                        "spent_usd": 10,
                    },
                    "competition_view": {
                        "session_id": "s",
                        "asset_id": "b",
                        "html_projection_sha": "sha",
                        "view_requested": True,
                        "twin_bound": True,
                        "claimed_format": "html",
                        "competition": {
                            "draft_id": "d",
                            "parent_asset_id": "b",
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
                                    "title": "P",
                                    "external_id": "arxiv:1",
                                }
                            ],
                            "quality_overall": 0.9,
                            "would_exceed": False,
                            "search_query": "p",
                        },
                    },
                },
            },
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
