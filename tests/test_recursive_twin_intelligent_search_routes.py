"""Hermetic tests for twin intelligent search routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.recursive_twin_intelligent_search_routes import (
    register_recursive_twin_intelligent_search_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_recursive_twin_intelligent_search_routes(app)
    return TestClient(app)


def test_search_ok() -> None:
    r = _client().post(
        "/twins/intelligent-search/search",
        json={
            "query": "scaling",
            "records": [
                {
                    "twin_id": "t1",
                    "parent_asset_id": "a1",
                    "insights": ["scaling laws hold"],
                    "questions": [],
                }
            ],
            "limit": 20,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remote_index_queried"] is False
    assert len(body["hits"]) == 1


def test_empty_query_400() -> None:
    r = _client().post(
        "/twins/intelligent-search/search",
        json={"query": "  ", "records": []},
    )
    # min_length=1 may 422; whitespace may 400 from pure layer
    assert r.status_code in (400, 422)


def test_extra_forbid() -> None:
    r = _client().post(
        "/twins/intelligent-search/search",
        json={
            "query": "scaling",
            "records": [],
            "remote_index_queried": True,
        },
    )
    assert r.status_code == 422


def test_zero_hits() -> None:
    r = _client().post(
        "/twins/intelligent-search/search",
        json={
            "query": "quantum teleportation",
            "records": [
                {
                    "twin_id": "t1",
                    "parent_asset_id": "a1",
                    "insights": ["cooking notes"],
                    "questions": [],
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["hits"] == []
    assert r.json()["remote_index_queried"] is False
