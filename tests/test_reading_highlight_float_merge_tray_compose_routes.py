"""Route tests for reading highlight float merge tray compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.reading_highlight_float_merge_tray_compose_routes import (
    register_reading_highlight_float_merge_tray_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_reading_highlight_float_merge_tray_compose_routes(app)
    return TestClient(app)


def test_compose_spawn_only():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-merge-tray/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "scaling laws under noise",
            "gated": False,
            "preferred_view_mode": "floating",
            "would_exceed": False,
            "source_families": ["arxiv"],
            "surface_action": "spawn_only",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["surface_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["pack_dispatched"] is False
    assert body["tray"] is None
    assert body["launch"]["launch_ready"] is True


def test_compose_tray_collective():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-merge-tray/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "new highlight",
            "gated": False,
            "would_exceed": False,
            "surface_action": "tray_collective",
            "operator_ack": True,
            "existing_members": [
                {
                    "instance_id": "existing-1",
                    "parent_asset_id": "book-1",
                    "status": "completed",
                    "live_dispatched": False,
                    "merge_executed": False,
                }
            ],
            "selected_instance_ids": ["existing-1"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tray"]["action"] == "collective_pack"
    assert body["pack_dispatched"] is False
    assert body["live_dispatched"] is False


def test_compose_gated_400():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-merge-tray/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "secret",
            "gated": True,
            "would_exceed": False,
            "surface_action": "spawn_only",
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"].lower()


def test_compose_full_merge_not_ready():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-merge-tray/compose",
        json={
            "parent_asset_id": "book-1",
            "highlight": "claim C",
            "gated": False,
            "would_exceed": False,
            "surface_action": "spawn_and_full_merge",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["surface_ready"] is False
    assert body["tray"]["tray_ready"] is False
    assert body["merge_executed"] is False
