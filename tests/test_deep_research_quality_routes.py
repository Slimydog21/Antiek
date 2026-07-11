"""Hermetic tests for deep research quality routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.deep_research_quality_routes import (
    register_deep_research_quality_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_deep_research_quality_routes(app)
    return TestClient(app)


def test_evaluate_ok() -> None:
    r = _client().post(
        "/research/quality-rubric/evaluate",
        json={
            "research_id": "dr-1",
            "dimensions": [
                {"dimension": "citation_density", "score": 0.8},
                {"dimension": "intellectual_honesty", "score": 0.9},
            ],
            "require_all_dimensions": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["persisted"] is False
    assert body["overall"] is not None
    assert body["authority"] == "deep_research_quality_rubric_advisory"


def test_empty_overall_null() -> None:
    r = _client().post(
        "/research/quality-rubric/evaluate",
        json={"research_id": "dr-2", "dimensions": []},
    )
    assert r.status_code == 200
    assert r.json()["overall"] is None
    assert r.json()["persisted"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/quality-rubric/evaluate",
        json={
            "research_id": "dr",
            "dimensions": [],
            "persisted": True,
        },
    )
    assert r.status_code == 422


def test_strict_bool() -> None:
    r = _client().post(
        "/research/quality-rubric/evaluate",
        json={
            "research_id": "dr",
            "dimensions": [],
            "require_all_dimensions": "false",
        },
    )
    assert r.status_code == 422
