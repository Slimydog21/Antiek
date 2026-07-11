"""Hermetic tests for floating draft combined routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.floating_research_draft_combined_document_routes import (
    register_floating_research_draft_combined_document_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_floating_research_draft_combined_document_routes(app)
    return TestClient(app)


def test_compose_ok() -> None:
    r = _client().post(
        "/research/floating-draft-combined/compose",
        json={
            "parent_asset_id": "asset-1",
            "parent_excerpt": "<p>body</p>",
            "operator_ack": False,
            "sources": [
                {
                    "instance_id": "fdr_1",
                    "parent_asset_id": "asset-1",
                    "status": "completed",
                    "highlight": "scaling",
                    "findings": ["claim A"],
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft_written"] is False
    assert body["merge_executed"] is False
    assert body["draft_ready"] is True
    assert body["authority"] == "floating_research_draft_combined_document_advisory"


def test_closed_400() -> None:
    r = _client().post(
        "/research/floating-draft-combined/compose",
        json={
            "parent_asset_id": "a",
            "operator_ack": False,
            "sources": [
                {
                    "instance_id": "f1",
                    "parent_asset_id": "a",
                    "status": "closed",
                    "findings": ["x"],
                }
            ],
        },
    )
    assert r.status_code == 400
    assert "not closed" in r.json()["detail"]


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/floating-draft-combined/compose",
        json={
            "parent_asset_id": "a",
            "operator_ack": False,
            "sources": [
                {
                    "instance_id": "f1",
                    "parent_asset_id": "a",
                    "status": "completed",
                    "findings": ["x"],
                }
            ],
            "draft_written": True,
        },
    )
    assert r.status_code == 422
