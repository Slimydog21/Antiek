"""Hermetic tests for Antiek-bench recursive rewrite routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_recursive_rewrite_routes import (
    register_antiek_bench_recursive_rewrite_routes,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_recursive_rewrite_routes(app)
    return TestClient(app)


def test_propose_ok() -> None:
    r = _client().post(
        "/settings/antiek-bench/recursive-rewrite/propose",
        json={
            "week_label": "2026-W28",
            "patterns": [
                {
                    "task_family": "citation_binding",
                    "model_id": "model-a",
                    "outcome": "failed",
                    "n": 3,
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False
    assert len(body["proposals"]) == 1


def test_empty_ok() -> None:
    r = _client().post(
        "/settings/antiek-bench/recursive-rewrite/propose",
        json={"week_label": "2026-W28", "patterns": []},
    )
    assert r.status_code == 200
    assert r.json()["applied"] is False
    assert r.json()["proposals"] == []


def test_extra_forbid() -> None:
    r = _client().post(
        "/settings/antiek-bench/recursive-rewrite/propose",
        json={
            "week_label": "w",
            "patterns": [],
            "applied": True,
        },
    )
    assert r.status_code == 422
