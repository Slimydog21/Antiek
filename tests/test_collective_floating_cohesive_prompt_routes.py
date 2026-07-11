"""Hermetic tests for collective floating cohesive prompt routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.collective_floating_cohesive_prompt_routes import (
    register_collective_floating_cohesive_prompt_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_collective_floating_cohesive_prompt_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/research/collective-cohesive-prompt/build",
        json={
            "members": [
                {
                    "instance_id": "fdr_1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "highlight": "scaling",
                },
                {
                    "instance_id": "fdr_2",
                    "parent_asset_id": "asset-1",
                    "status": "open",
                },
            ],
            "cohesive_prompt": "Reconcile claims",
            "operator_ack": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_dispatched"] is False
    assert body["pack_ready"] is True
    assert body["member_count"] == 2
    assert body["authority"] == "collective_floating_cohesive_prompt_advisory"


def test_no_ack_pack_not_ready() -> None:
    r = _client().post(
        "/research/collective-cohesive-prompt/build",
        json={
            "members": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
            ],
            "cohesive_prompt": "Continue",
            "operator_ack": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["pack_ready"] is False
    assert r.json()["live_dispatched"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/collective-cohesive-prompt/build",
        json={
            "members": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
            ],
            "cohesive_prompt": "x",
            "operator_ack": False,
            "live_dispatched": True,
        },
    )
    assert r.status_code == 422


def test_closed_member_400() -> None:
    r = _client().post(
        "/research/collective-cohesive-prompt/build",
        json={
            "members": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "p",
                    "status": "closed",
                },
            ],
            "cohesive_prompt": "x",
            "operator_ack": False,
        },
    )
    assert r.status_code == 400
    assert "not closed" in r.json()["detail"]
