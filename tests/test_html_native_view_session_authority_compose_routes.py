"""Route tests for HTML-native view session authority."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_view_session_authority_compose_routes import (
    register_html_native_view_session_authority_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_view_session_authority_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/html-native-view-session-authority/compose",
        json={
            "session_id": "sess-1",
            "asset_id": "asset-1",
            "html_projection_sha": "sha-html",
            "view_requested": True,
            "twin_bound": True,
            "twin_substrate_ready": True,
            "claimed_format": "html",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["pdf_view_authorized"] is False
    assert body["pdf_primary"] is False
    assert body["store_mutated"] is False
