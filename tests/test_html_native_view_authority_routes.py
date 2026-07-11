"""Hermetic tests for HTML-native view authority routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_native_view_authority_routes import (
    register_html_native_view_authority_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_native_view_authority_routes(app)
    return TestClient(app)


def test_evaluate_ready() -> None:
    r = _client().post(
        "/assets/html-native-view/evaluate",
        json={
            "asset_id": "book-1",
            "asset_kind": "book",
            "source_format": "pdf",
            "html_projection_sha": "sha256:ready",
            "prefer_html": True,
            "allow_pdf_secondary": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["human_viewable_html"] is True
    assert body["primary_format"] == "html"


def test_evaluate_not_ready() -> None:
    r = _client().post(
        "/assets/html-native-view/evaluate",
        json={
            "asset_id": "book-1",
            "asset_kind": "book",
            "source_format": "pdf",
            "html_projection_sha": None,
        },
    )
    assert r.status_code == 200
    assert r.json()["human_viewable_html"] is False
    assert r.json()["primary_format"] == "unavailable"


def test_extra_forbid() -> None:
    r = _client().post(
        "/assets/html-native-view/evaluate",
        json={
            "asset_id": "a",
            "asset_kind": "book",
            "source_format": "pdf",
            "human_viewable_html": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/assets/html-native-view/evaluate",
        json={
            "asset_id": "a",
            "asset_kind": "book",
            "source_format": "pdf",
            "prefer_html": "true",
        },
    )
    assert r.status_code == 422
