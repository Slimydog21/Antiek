"""Route tests for write-mode twin collective analysis compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.write_mode_twin_collective_analysis_compose_routes import (
    register_write_mode_twin_collective_analysis_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_write_mode_twin_collective_analysis_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/write-mode-twin-collective-analysis/compose",
        json={
            "session_id": "sess-1",
            "draft_id": "draft-1",
            "parent_asset_id": "asset-1",
            "twin_slices": [
                {
                    "parent_asset_id": "asset-1",
                    "insights": ["insight A"],
                    "questions": ["question A?"],
                },
                {
                    "parent_asset_id": "asset-2",
                    "insights": ["insight B"],
                    "questions": [],
                },
            ],
            "base_draft_html": "<p>Open</p>",
            "chase_slots": [
                {
                    "slot_id": "s1",
                    "question_id": "q1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["f1"],
                    "body": "Evidence?",
                },
                {
                    "slot_id": "s2",
                    "question_id": "q2",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["f2"],
                    "body": "Counter?",
                },
            ],
            "analysis_kind": "draft_analysis",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["draft_written"] is False
    assert body["analysis_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
