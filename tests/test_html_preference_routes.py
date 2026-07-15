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


def test_route_is_mounted_in_production_app(monkeypatch) -> None:
    """The client contract must be reachable from the real app factory."""
    for name in (
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_SESSION_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    from interfaces.research.api.app import create_app

    client = TestClient(
        create_app(
            register_wrestling=False,
            register_providers=False,
            cors_origins=[],
        )
    )
    response = client.post(
        "/assets/view-preference/decide",
        json={"html_ready": True, "pdf_available": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "html"
