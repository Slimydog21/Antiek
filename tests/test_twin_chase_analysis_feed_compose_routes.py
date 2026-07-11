"""Route tests for twin chase analysis feed compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_chase_analysis_feed_compose_routes import (
    register_twin_chase_analysis_feed_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_chase_analysis_feed_compose_routes(app)
    return TestClient(app)


def test_compose_ok():
    c = _client()
    r = c.post(
        "/research/twin-chase-analysis-feed/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "paper-1",
            "findings": [
                {
                    "source_id": "chase_1",
                    "body": "scaling holds",
                    "kind": "insight",
                },
                {
                    "source_id": "chase_2",
                    "body": "failure mode?",
                    "kind": "question",
                },
            ],
            "analysis_excerpt": "draft analysis",
            "mark_for_prompt_context": True,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feed_ready"] is True
    assert body["twin_written"] is False
    assert body["record_persisted"] is False
    assert body["prompts_injected"] is False
    assert body["live_dispatch_authorized"] is False


def test_compose_empty_400():
    c = _client()
    r = c.post(
        "/research/twin-chase-analysis-feed/compose",
        json={
            "session_id": "s",
            "parent_asset_id": "p",
            "findings": [],
            "operator_ack": True,
        },
    )
    assert r.status_code == 422  # pydantic min_length or 400
