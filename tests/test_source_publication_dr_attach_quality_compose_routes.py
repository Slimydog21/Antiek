"""Route tests for source publication DR attach quality."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_publication_dr_attach_quality_compose_routes import (
    register_source_publication_dr_attach_quality_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_publication_dr_attach_quality_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/source-publication-dr-attach-quality/compose",
        json={
            "session_id": "sess-1",
            "parent_asset_id": "asset-1",
            "requested_families": ["arxiv", "substack"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Paper",
                    "html_fragment": "<p>x</p>",
                },
                {
                    "source_id": "sub-1",
                    "family": "substack",
                    "title": "Essay",
                    "html_fragment": "<p>y</p>",
                },
            ],
            "quality_overall": 0.85,
            "quality_floor": 0.7,
            "would_exceed": False,
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["remote_fetched"] is False
    assert body["pdf_view_authorized"] is False
    assert body["live_dispatch_authorized"] is False
