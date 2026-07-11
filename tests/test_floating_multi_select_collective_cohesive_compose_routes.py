"""Route tests for floating multi-select collective cohesive compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_multi_select_collective_cohesive_compose_routes import (
    register_floating_multi_select_collective_cohesive_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_multi_select_collective_cohesive_compose_routes(app)
    return TestClient(app)


def test_compose_cohesive_prompt():
    c = _client()
    r = c.post(
        "/research/floating-multi-select-collective-cohesive/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "members": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "asset-1",
                    "status": "open",
                    "highlight": "h1",
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["f1"],
                },
            ],
            "selected_instance_ids": ["a", "b"],
            "pack_mode": "cohesive_prompt",
            "cohesive_prompt": "Synthesize as unit",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["pack_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["analysis_written"] is False
    assert body["cohesive"] is not None


def test_compose_plus_analysis_draft():
    c = _client()
    r = c.post(
        "/research/floating-multi-select-collective-cohesive/compose",
        json={
            "session_id": "sess-2",
            "parent_asset_id": "asset-1",
            "members": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["fa"],
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["fb"],
                },
            ],
            "selected_instance_ids": ["a", "b"],
            "pack_mode": "cohesive_plus_analysis",
            "cohesive_prompt": "Draft analysis",
            "operator_ack": True,
            "analysis_kind": "draft_analysis",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["analysis"]["kind"] == "draft_analysis"
    assert body["analysis_written"] is False
