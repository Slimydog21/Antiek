"""Red-proofs: HTML preference HTTP route."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_preference_routes import (
    register_html_preference_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_html_preference_routes(app)
    return TestClient(app)


def test_html_ready_wins() -> None:
    r = _client().post(
        "/assets/view-preference/decide",
        json={
            "html_ready": True,
            "pdf_available": True,
            "require_html": True,
            "asset_id": "doc-1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "html"
    assert body["preferred"] is True
    assert body["reason"] == "html_ready"


def test_pdf_blocked_when_require_html() -> None:
    r = _client().post(
        "/assets/view-preference/decide",
        json={"html_ready": False, "pdf_available": True, "require_html": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "metadata_only"
    assert body["preferred"] is False


def test_pdf_fallback_when_allowed() -> None:
    r = _client().post(
        "/assets/view-preference/decide",
        json={"html_ready": False, "pdf_available": True, "require_html": False},
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "pdf"
    assert r.json()["preferred"] is False


def test_string_bool_rejected() -> None:
    r = _client().post(
        "/assets/view-preference/decide",
        json={"html_ready": "false", "pdf_available": True},
    )
    assert r.status_code == 422


def test_unavailable() -> None:
    r = _client().post(
        "/assets/view-preference/decide",
        json={"html_ready": False, "pdf_available": False},
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "unavailable"
