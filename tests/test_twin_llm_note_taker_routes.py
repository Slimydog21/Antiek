"""Hermetic tests for note-taker routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_llm_note_taker_routes import (
    register_twin_llm_note_taker_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_llm_note_taker_routes(app)
    return TestClient(app)


def test_payload_ok() -> None:
    r = _client().post(
        "/twins/note-taker/payload",
        json={
            "parent_asset_id": "asset-1",
            "insights": ["a"],
            "questions": ["q?"],
            "llm_filled": True,
            "gated": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_invoked"] is False
    assert body["llm_filled"] is True


def test_empty_rejected() -> None:
    r = _client().post(
        "/twins/note-taker/payload",
        json={
            "parent_asset_id": "a",
            "insights": [],
            "questions": [],
            "llm_filled": False,
            "gated": False,
        },
    )
    assert r.status_code == 400


def test_missing_llm_filled_422() -> None:
    r = _client().post(
        "/twins/note-taker/payload",
        json={
            "parent_asset_id": "a",
            "insights": ["x"],
            "gated": False,
        },
    )
    assert r.status_code == 422


def test_extra_forbid() -> None:
    r = _client().post(
        "/twins/note-taker/payload",
        json={
            "parent_asset_id": "a",
            "insights": ["x"],
            "llm_filled": True,
            "gated": False,
            "model_invoked": True,
        },
    )
    assert r.status_code == 422
