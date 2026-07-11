"""Route tests for twin substrate search → merge compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_substrate_search_merge_compose_routes import (
    register_twin_substrate_search_merge_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_substrate_search_merge_compose_routes(app)
    return TestClient(app)


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/twin-substrate-search-merge/compose",
        json={
            "pack_id": "pack-1",
            "search_query": "scaling laws",
            "twin_records": [
                {
                    "twin_id": "twin-1",
                    "parent_asset_id": "asset-1",
                    "insights": [
                        "scaling laws hold under compute-optimal regimes"
                    ],
                    "questions": ["Does the law break?"],
                },
                {
                    "twin_id": "twin-2",
                    "parent_asset_id": "asset-2",
                    "insights": ["attention efficiency with scaling"],
                    "questions": ["What is the frontier?"],
                },
            ],
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pack_ready"] is True
    assert body["remote_index_queried"] is False
    assert body["merge_executed"] is False
    assert body["twin_written"] is False
    assert body["store_mutated"] is False
