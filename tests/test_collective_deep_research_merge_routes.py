"""Hermetic tests for collective analysis merge routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.collective_deep_research_merge_routes import (
    register_collective_deep_research_merge_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_collective_deep_research_merge_routes(app)
    return TestClient(app)


def test_draft_ok() -> None:
    r = _client().post(
        "/research/collective-analysis/merge",
        json={
            "instances": [
                {
                    "instance_id": "a",
                    "parent_asset_id": "p",
                    "status": "completed",
                    "findings": ["x"],
                },
                {
                    "instance_id": "b",
                    "parent_asset_id": "p",
                    "status": "completed",
                },
            ],
            "kind": "draft_analysis",
            "operator_ack": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["analysis_written"] is False
    assert body["kind"] == "draft_analysis"


def test_full_without_ack_400() -> None:
    r = _client().post(
        "/research/collective-analysis/merge",
        json={
            "instances": [
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
            "kind": "full_analysis",
            "operator_ack": False,
        },
    )
    assert r.status_code == 400


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/collective-analysis/merge",
        json={
            "instances": [
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
            "kind": "draft_analysis",
            "operator_ack": False,
            "analysis_written": True,
        },
    )
    assert r.status_code == 422
