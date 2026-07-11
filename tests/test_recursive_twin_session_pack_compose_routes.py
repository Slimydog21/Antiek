"""Hermetic tests for recursive twin session pack routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_session_pack_compose_routes import (
    register_recursive_twin_session_pack_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_session_pack_compose_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/twins/session-pack/compose",
        json={
            "session_id": "sess-1",
            "members": [
                {
                    "asset_id": "a1",
                    "twin_bound": True,
                    "insights": ["scaling holds"],
                    "questions": ["multimodal?"],
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["twin_store_mutated"] is False
    assert body["pack_ready"] is True
    assert body["authority"] == "recursive_twin_session_pack_compose_advisory"


def test_unbound_not_ready() -> None:
    r = _client().post(
        "/twins/session-pack/compose",
        json={
            "session_id": "s",
            "members": [
                {
                    "asset_id": "a1",
                    "twin_bound": False,
                    "insights": ["x"],
                    "questions": [],
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_store_mutated"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/twins/session-pack/compose",
        json={
            "session_id": "s",
            "members": [
                {
                    "asset_id": "a1",
                    "twin_bound": True,
                    "insights": [],
                    "questions": [],
                }
            ],
            "twin_store_mutated": True,
        },
    )
    assert r.status_code == 422
