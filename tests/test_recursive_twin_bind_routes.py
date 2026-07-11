"""Hermetic tests for recursive twin bind routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_bind_routes import (
    register_recursive_twin_bind_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_bind_routes(app)
    return TestClient(app)


def test_evaluate_ok() -> None:
    r = _client().post(
        "/twins/recursive-bind/evaluate",
        json={
            "parent_asset_id": "asset-1",
            "source": "operator",
            "llm_filled": False,
            "gated": False,
            "insights": ["one"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bind_allowed"] is True
    assert body["twin_created"] is False
    assert body["insights"] == ["one"]


def test_gated() -> None:
    r = _client().post(
        "/twins/recursive-bind/evaluate",
        json={
            "parent_asset_id": "asset-1",
            "source": "operator",
            "llm_filled": False,
            "gated": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["bind_allowed"] is False
    assert r.json()["twin_created"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/twins/recursive-bind/evaluate",
        json={
            "parent_asset_id": "a",
            "source": "operator",
            "llm_filled": False,
            "gated": False,
            "twin_created": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/twins/recursive-bind/evaluate",
        json={
            "parent_asset_id": "a",
            "source": "operator",
            "llm_filled": "false",
            "gated": False,
        },
    )
    assert r.status_code == 422


def test_llm_empty_400() -> None:
    r = _client().post(
        "/twins/recursive-bind/evaluate",
        json={
            "parent_asset_id": "a",
            "source": "llm_note_taker",
            "llm_filled": True,
            "gated": False,
        },
    )
    assert r.status_code == 400
