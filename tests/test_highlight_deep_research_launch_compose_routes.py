"""Route tests for highlight deep research launch compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.highlight_deep_research_launch_compose_routes import (
    register_highlight_deep_research_launch_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_highlight_deep_research_launch_compose_routes(app)
    return TestClient(app)


def test_compose_launch():
    c = _client()
    r = c.post(
        "/research/highlight-dr-launch/compose",
        json={
            "parent_asset_id": "asset-read-1",
            "highlight": "scaling laws under noise",
            "gated": False,
            "preferred_view_mode": "fullscreen",
            "would_exceed": False,
            "selected_model_id": "gpt-5",
            "source_families": ["arxiv", "substack"],
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["launch_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["preferred_view_mode"] == "fullscreen"
    assert body["source_family_count"] == 2
