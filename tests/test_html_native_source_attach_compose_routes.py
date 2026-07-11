"""Route tests for HTML-native source attach compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_source_attach_compose_routes import (
    register_html_native_source_attach_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_source_attach_compose_routes(app)
    return TestClient(app)


def test_compose_attach():
    c = _client()
    r = c.post(
        "/research/html-source-attach/compose",
        json={
            "session_id": "ws-1",
            "parent_asset_id": "asset-1",
            "requested_families": ["arxiv", "substack"],
            "operator_ack": True,
            "sources": [
                {
                    "source_id": "s1",
                    "family": "arxiv",
                    "title": "Scaling laws",
                    "html_fragment": "<article>x</article>",
                },
                {
                    "source_id": "s2",
                    "family": "substack",
                    "title": "Essay",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["attach_ready"] is True
    assert body["remote_fetched"] is False
    assert body["pdf_view_authorized"] is False
    assert body["store_mutated"] is False
    assert body["authority"] == "html_native_source_attach_compose_advisory"
