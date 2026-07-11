"""Hermetic tests for competition deep research gap routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_deep_research_gap_routes import (
    register_competition_deep_research_gap_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_deep_research_gap_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/research/competition-gap/build",
        json={
            "decisions": [
                {
                    "competitor": "Elicit",
                    "area": "citation_grounding",
                    "decision_summary": "Paper-grounded claims",
                    "antiek_status": "behind",
                    "residual": "Wire citation spans",
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["backlog_mutated"] is False
    assert body["behind_count"] == 1
    assert body["authority"] == "competition_deep_research_gap_advisory"


def test_empty_ok() -> None:
    r = _client().post(
        "/research/competition-gap/build",
        json={"decisions": []},
    )
    assert r.status_code == 200
    assert r.json()["behind_count"] == 0
    assert r.json()["backlog_mutated"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/competition-gap/build",
        json={
            "decisions": [],
            "backlog_mutated": True,
        },
    )
    assert r.status_code == 422


def test_invalid_status_422() -> None:
    r = _client().post(
        "/research/competition-gap/build",
        json={
            "decisions": [
                {
                    "competitor": "X",
                    "area": "source_acquisition",
                    "decision_summary": "y",
                    "antiek_status": "winning",
                }
            ]
        },
    )
    assert r.status_code == 422
