"""Route tests for floating fullscreen open compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    register_floating_fullscreen_open_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_fullscreen_open_compose_routes(app)
    return TestClient(app)


def test_compose_spawn():
    c = _client()
    r = c.post(
        "/research/floating-fullscreen-open/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "highlight": "Key claim",
            "prompt": "Research this",
            "gated": False,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fullscreen_ready"] is True
    assert body["instance"]["view_mode"] == "fullscreen"
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["pack_dispatched"] is False
