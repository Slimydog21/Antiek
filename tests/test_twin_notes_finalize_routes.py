"""Red-proofs: finalize authorize HTTP surface (no app.py)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_finalize_routes import (
    register_twin_notes_finalize_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_notes_finalize_routes(app)
    return TestClient(app)


def test_authorize_ok() -> None:
    c = _client()
    r = c.post(
        "/twins/finalize/authorize",
        json={
            "draft_id": "draft-1",
            "parent_asset_id": "parent-1",
            "provisional": True,
            "operator_accepted": True,
            "twin_ids": ["t1"],
            "twin_parent_ids": ["parent-1"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorized"] is True
    assert body["reason"] == "ok"
    assert "not performed here" in " ".join(body["notes"])


def test_deny_without_accept() -> None:
    c = _client()
    r = c.post(
        "/twins/finalize/authorize",
        json={
            "draft_id": "draft-1",
            "parent_asset_id": "parent-1",
            "provisional": True,
            "operator_accepted": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["authorized"] is False
    assert body["reason"] == "operator_accept_required"


def test_deny_non_provisional() -> None:
    c = _client()
    r = c.post(
        "/twins/finalize/authorize",
        json={
            "draft_id": "draft-1",
            "parent_asset_id": "parent-1",
            "provisional": False,
            "operator_accepted": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["authorized"] is False
    assert r.json()["reason"] == "not_provisional_draft"


def test_cross_parent_denied() -> None:
    c = _client()
    r = c.post(
        "/twins/finalize/authorize",
        json={
            "draft_id": "draft-1",
            "parent_asset_id": "p1",
            "provisional": True,
            "operator_accepted": True,
            "twin_parent_ids": ["p1", "p2"],
        },
    )
    assert r.status_code == 200
    assert r.json()["reason"] == "cross_parent_twins"


def test_malformed_empty_id_422_or_400() -> None:
    c = _client()
    r = c.post(
        "/twins/finalize/authorize",
        json={
            "draft_id": "",
            "parent_asset_id": "p",
            "provisional": True,
            "operator_accepted": True,
        },
    )
    # pydantic min_length may 422 before gate
    assert r.status_code in (400, 422)
