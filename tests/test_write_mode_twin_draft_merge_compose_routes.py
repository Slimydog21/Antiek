"""Route tests for write-mode twin draft merge compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.write_mode_twin_draft_merge_compose_routes import (
    register_write_mode_twin_draft_merge_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_write_mode_twin_draft_merge_compose_routes(app)
    return TestClient(app)


def test_compose_draft():
    c = _client()
    r = c.post(
        "/research/write-twin-draft/compose",
        json={
            "draft_id": "draft-1",
            "base_draft_html": "<p>Opening</p>",
            "operator_ack": True,
            "slices": [
                {
                    "parent_asset_id": "a1",
                    "insights": ["claim holds"],
                    "questions": ["why?"],
                }
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["draft_ready"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["store_mutated"] is False
