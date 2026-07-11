"""Red-proofs: NotDiamond shadow HTTP surface (no app.py)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.notdiamond_shadow_routes import (
    register_notdiamond_shadow_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_notdiamond_shadow_routes(app)
    return TestClient(app)


def test_shadow_default_off() -> None:
    c = _client()
    r = c.post(
        "/settings/notdiamond/shadow",
        json={
            "local_model_id": "m1",
            "nd_recommended_model_id": "nd-would",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authority"] == "shadow"
    assert body["enabled"] is False
    assert body["nd_recommended_model_id"] is None


def test_shadow_enabled_agreement() -> None:
    c = _client()
    r = c.post(
        "/settings/notdiamond/shadow",
        json={
            "local_model_id": "m1",
            "nd_recommended_model_id": "m1",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["authority"] == "shadow"
    assert body["agreement"] is True


def test_empty_local_400() -> None:
    c = _client()
    r = c.post(
        "/settings/notdiamond/shadow",
        json={"local_model_id": "  "},
    )
    # pydantic min_length may 422 or gate 400
    assert r.status_code in (400, 422)
