"""Route tests for reading highlight float + twin feed compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.reading_highlight_float_twin_feed_compose_routes import (
    register_reading_highlight_float_twin_feed_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_reading_highlight_float_twin_feed_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-twin-feed/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "highlight": "scaling laws under noise",
            "gated": False,
            "would_exceed": False,
            "surface_action": "spawn_only",
            "operator_ack": True,
            "source_families": ["arxiv"],
            "twin_findings": [
                {
                    "source_id": "extra-1",
                    "body": "claim A supported",
                    "kind": "insight",
                }
            ],
            "mark_for_prompt_context": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["live_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["pack_dispatched"] is False
    assert body["twin_written"] is False
    assert body["record_persisted"] is False


def test_compose_gated_400():
    c = _client()
    r = c.post(
        "/research/reading-highlight-float-twin-feed/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "b",
            "highlight": "secret",
            "gated": True,
            "would_exceed": False,
            "surface_action": "spawn_only",
            "operator_ack": True,
        },
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"].lower()
