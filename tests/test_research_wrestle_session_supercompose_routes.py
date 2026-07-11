"""Route tests for research wrestle session super-compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_wrestle_session_supercompose_routes import (
    register_research_wrestle_session_supercompose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_wrestle_session_supercompose_routes(app)
    return TestClient(app)


def test_compose_ready():
    c = _client()
    r = c.post(
        "/research/wrestle-session/compose",
        json={
            "session_id": "ws-1",
            "parent_asset_id": "asset-1",
            "floating_instance_count": 2,
            "completed_floating_count": 1,
            "twin_insight_count": 3,
            "twin_question_count": 1,
            "open_question_count": 1,
            "source_family_count": 2,
            "citation_pack_ready": True,
            "quality_overall": 0.9,
            "would_exceed": False,
            "preferred_view_mode": "floating",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["wrestle_ready"] is True
    assert body["live_dispatch_authorized"] is False
    assert body["authority"] == "research_wrestle_session_supercompose_advisory"


def test_compose_budget_unknown_not_ready():
    c = _client()
    r = c.post(
        "/research/wrestle-session/compose",
        json={
            "session_id": "ws-1",
            "parent_asset_id": "asset-1",
            "floating_instance_count": 1,
            "completed_floating_count": 0,
            "twin_insight_count": 0,
            "twin_question_count": 0,
            "open_question_count": 1,
            "source_family_count": 1,
            "citation_pack_ready": False,
            "quality_overall": 0.8,
            "would_exceed": None,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["wrestle_ready"] is False
    assert body["live_dispatch_authorized"] is False
