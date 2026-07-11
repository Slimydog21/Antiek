"""Route tests for floating research view-mode compose (registerable)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_research_view_mode_compose_routes import (
    register_floating_research_view_mode_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_research_view_mode_compose_routes(app)
    return TestClient(app)


def test_spawn_and_compose_fullscreen():
    c = _client()
    r = c.post(
        "/research/floating-view-mode/spawn-and-compose",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "scaling laws",
            "gated": False,
            "action": "fullscreen",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["view_mode"] == "fullscreen"
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["action_applied"] is True
    assert body["authority"] == "floating_research_view_mode_compose_advisory"


def test_spawn_and_compose_full_merge_requires_completed_ack():
    c = _client()
    r = c.post(
        "/research/floating-view-mode/spawn-and-compose",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "scaling laws",
            "gated": False,
            "action": "propose_full_merge",
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
    r2 = c.post(
        "/research/floating-view-mode/spawn-and-compose",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "scaling laws",
            "gated": False,
            "mark_completed": True,
            "action": "propose_full_merge",
            "operator_ack": True,
        },
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["merge_intent"]["kind"] == "full_merge"
    assert body["merge_intent"]["merge_executed"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False


def test_compose_draft_merge_from_instance_body():
    c = _client()
    r = c.post(
        "/research/floating-view-mode/compose",
        json={
            "instance": {
                "instance_id": "fdr_1",
                "parent_asset_id": "a",
                "highlight": "h",
                "prompt": "p",
                "view_mode": "floating",
                "status": "open",
                "live_dispatched": False,
                "merge_executed": False,
            },
            "action": "propose_draft_merge",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["merge_intent"]["kind"] == "draft_merge"
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
