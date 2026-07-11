"""Route tests for floating draft-before-full-merge gate."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_draft_before_full_merge_gate_compose_routes import (
    register_floating_draft_before_full_merge_gate_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_draft_before_full_merge_gate_compose_routes(app)
    return TestClient(app)


def test_compose_draft_only():
    c = _client()
    r = c.post(
        "/research/floating-draft-before-full-merge-gate/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "parent_excerpt": "parent",
            "sources": [
                {
                    "instance_id": "f1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "findings": ["evidence"],
                }
            ],
            "stage": "draft_only",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gate_ready"] is True
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False


def test_compose_promote():
    c = _client()
    r = c.post(
        "/research/floating-draft-before-full-merge-gate/compose",
        json={
            "session_id": "sess-2",
            "parent_asset_id": "asset-1",
            "sources": [
                {
                    "instance_id": "f1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "highlight": "h",
                    "findings": ["f"],
                }
            ],
            "stage": "promote_full_merge",
            "operator_ack": True,
            "full_merge_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["full_merge_intent_ready"] is True
    assert body["merge_executed"] is False
