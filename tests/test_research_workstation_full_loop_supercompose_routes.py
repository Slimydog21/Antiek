"""Route tests for research workstation full-loop super-compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.research_workstation_full_loop_supercompose_routes import (
    register_research_workstation_full_loop_supercompose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_research_workstation_full_loop_supercompose_routes(app)
    return TestClient(app)


def test_compose_full_loop():
    c = _client()
    r = c.post(
        "/research/full-loop/compose",
        json={
            "wrestle": {
                "session_id": "ws-1",
                "parent_asset_id": "asset-1",
                "floating_instance_count": 2,
                "completed_floating_count": 1,
                "twin_insight_count": 2,
                "twin_question_count": 1,
                "open_question_count": 1,
                "source_family_count": 2,
                "citation_pack_ready": True,
                "quality_overall": 0.9,
                "would_exceed": False,
                "preferred_view_mode": "floating",
            },
            "source_attach": {
                "attach_ready": True,
                "remote_fetched": False,
                "source_count": 2,
            },
            "view_mode": {
                "preferred_view_mode": "floating",
                "floating_instance_count": 2,
            },
            "budget": {
                "would_exceed": False,
                "selected_model_id": "gpt-5",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["full_loop_ready"] is True
    assert body["live_dispatch_authorized"] is False
