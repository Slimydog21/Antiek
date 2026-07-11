"""Route tests for HTML asset view session compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_asset_view_session_compose_routes import (
    register_html_asset_view_session_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_asset_view_session_compose_routes(app)
    return TestClient(app)


def test_compose_view_session():
    c = _client()
    r = c.post(
        "/research/html-asset-view/compose",
        json={
            "session_id": "vs-1",
            "asset_id": "asset-1",
            "html_projection_sha": "sha-html-1",
            "view_requested": True,
            "twin_bound": True,
            "twin_substrate_ready": True,
            "claimed_format": "html",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_ready"] is True
    assert body["pdf_view_authorized"] is False
    assert body["store_mutated"] is False
