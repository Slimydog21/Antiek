"""Route tests for floating instance tray compose."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_instance_tray_compose_routes import (
    register_floating_instance_tray_compose_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_instance_tray_compose_routes(app)
    return TestClient(app)


def test_compose_tray():
    c = _client()
    r = c.post(
        "/research/floating-tray/compose",
        json={
            "parent_asset_id": "asset-1",
            "members": [
                {
                    "instance_id": "f1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "live_dispatched": False,
                    "merge_executed": False,
                },
                {
                    "instance_id": "f2",
                    "parent_asset_id": "asset-1",
                    "status": "open",
                    "live_dispatched": False,
                    "merge_executed": False,
                },
            ],
            "selected_instance_ids": ["f1", "f2"],
            "action": "collective_pack",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tray_ready"] is True
    assert body["pack_dispatched"] is False
    assert body["merge_executed"] is False
    assert body["live_dispatched"] is False
