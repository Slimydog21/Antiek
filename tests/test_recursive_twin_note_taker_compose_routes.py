"""Route tests for recursive twin note-taker compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_note_taker_compose_routes import (
    register_recursive_twin_note_taker_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_note_taker_compose_routes(app)
    return TestClient(app)


def test_compose_twin_note_taker():
    c = _client()
    r = c.post(
        "/research/recursive-twin-note-taker/compose",
        json={
            "parent_asset_id": "asset-1",
            "source_excerpt": "<p>Scaling laws</p>",
            "operator_ack": True,
            "focus_questions": ["What is the sample size?"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["twin_propose_ready"] is True
    assert body["twin_written"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False
