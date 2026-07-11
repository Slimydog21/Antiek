"""Hermetic tests for highlight twin seed routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_from_highlight_routes import (
    register_twin_from_highlight_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_from_highlight_routes(app)
    return TestClient(app)


def test_seed_ok() -> None:
    r = _client().post(
        "/twins/from-highlight/seed",
        json={
            "parent_asset_id": "asset-1",
            "highlight": "A key sentence.",
            "insights": ["insight"],
            "questions": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm_filled"] is False
    assert body["authority"] == "highlight_seed_only"
    assert body["highlight"] == "A key sentence."


def test_gated_400() -> None:
    r = _client().post(
        "/twins/from-highlight/seed",
        json={
            "parent_asset_id": "a",
            "highlight": "secret",
            "gated": True,
        },
    )
    assert r.status_code == 400
    assert "gated" in r.json()["detail"]


def test_extra_forbid() -> None:
    r = _client().post(
        "/twins/from-highlight/seed",
        json={
            "parent_asset_id": "a",
            "highlight": "x",
            "llm_filled": True,
        },
    )
    assert r.status_code == 422
