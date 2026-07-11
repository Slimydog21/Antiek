"""Hermetic tests for competition gap residual plan routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.competition_gap_residual_plan_routes import (
    register_competition_gap_residual_plan_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_competition_gap_residual_plan_routes(app)
    return TestClient(app)


def test_build_ok() -> None:
    r = _client().post(
        "/research/competition-gap-residual-plan/build",
        json={
            "decisions": [
                {
                    "competitor": "Elicit",
                    "area": "citation_grounding",
                    "decision_summary": "spans",
                    "antiek_status": "behind",
                    "residual": "Wire spans",
                },
                {
                    "competitor": "C",
                    "area": "evaluation_harness",
                    "decision_summary": "meta",
                    "antiek_status": "unknown",
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["backlog_mutated"] is False
    assert body["item_count"] == 2
    assert body["p0_count"] == 1
    assert body["authority"] == "competition_gap_residual_plan_advisory"


def test_max_items() -> None:
    r = _client().post(
        "/research/competition-gap-residual-plan/build",
        json={
            "max_items": 1,
            "decisions": [
                {
                    "competitor": "Elicit",
                    "area": "citation_grounding",
                    "decision_summary": "spans",
                    "antiek_status": "behind",
                    "residual": "Wire spans",
                },
                {
                    "competitor": "X",
                    "area": "model_routing",
                    "decision_summary": "r",
                    "antiek_status": "behind",
                },
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["item_count"] == 1
    assert r.json()["backlog_mutated"] is False


def test_extra_forbid() -> None:
    r = _client().post(
        "/research/competition-gap-residual-plan/build",
        json={"decisions": [], "backlog_mutated": True},
    )
    assert r.status_code == 422


def test_empty_ok() -> None:
    r = _client().post(
        "/research/competition-gap-residual-plan/build",
        json={"decisions": []},
    )
    assert r.status_code == 200
    assert r.json()["item_count"] == 0
    assert r.json()["backlog_mutated"] is False
