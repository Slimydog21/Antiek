"""Route tests for twin substrate cross-asset merge compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_substrate_cross_asset_merge_compose_routes import (
    register_twin_substrate_cross_asset_merge_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_substrate_cross_asset_merge_compose_routes(app)
    return TestClient(app)


def test_compose_merge_pack():
    c = _client()
    r = c.post(
        "/research/twin-cross-asset-merge/compose",
        json={
            "pack_id": "pack-1",
            "operator_ack": True,
            "slices": [
                {
                    "parent_asset_id": "a1",
                    "insights": ["claim holds"],
                    "questions": ["why?"],
                },
                {
                    "parent_asset_id": "a2",
                    "insights": ["routing non-linear"],
                    "questions": [],
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["merge_ready"] is True
    assert body["merge_executed"] is False
    assert body["twin_written"] is False
    assert body["store_mutated"] is False
