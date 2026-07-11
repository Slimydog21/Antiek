"""Red-proofs: price ceiling HTTP surface (no app.py)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.price_ceiling_routes import register_price_ceiling_routes


def _client() -> TestClient:
    app = FastAPI()
    register_price_ceiling_routes(app)
    return TestClient(app)


def test_recommend_ok() -> None:
    c = _client()
    r = c.post(
        "/midnight-oil/price-ceiling/recommend",
        json={
            "hours": 2,
            "goals": ["a", "b"],
            "usd_per_hour_low": 1,
            "usd_per_hour_high": 3,
            "usd_per_goal": 0.5,
            "contingency_fraction": 0.1,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authority"] == "advisory"
    assert body["goal_count"] == 2
    assert body["recommended_ceiling_usd"] == 5.5
    assert body["low_usd"] == 3.0
    assert body["high_usd"] == 7.0


def test_bad_hours_400() -> None:
    c = _client()
    r = c.post(
        "/midnight-oil/price-ceiling/recommend",
        json={"hours": 0, "goals": []},
    )
    assert r.status_code == 400
    assert "hours" in r.json()["detail"].lower()


def test_authority_always_advisory() -> None:
    c = _client()
    r = c.post(
        "/midnight-oil/price-ceiling/recommend",
        json={"hours": 1, "goals": 0},
    )
    assert r.status_code == 200
    assert r.json()["authority"] == "advisory"
