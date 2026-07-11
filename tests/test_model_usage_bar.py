"""Red-proofs: usage bar + prompt projection honesty."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_usage_bar_routes import (
    register_model_usage_bar_routes,
)
from substrate.model_decision.usage_bar import (
    compute_usage_bar,
    project_prompt_against_bar,
)


def test_unknown_spent_or_cap_null_remaining() -> None:
    bar = compute_usage_bar(daily_cap_usd=10.0, spent_usd=None)
    assert bar.remaining_usd is None
    assert bar.fraction_used is None
    assert bar.over_budget is None
    assert any("spent_usd unknown" in n for n in bar.notes)

    bar2 = compute_usage_bar(daily_cap_usd=None, spent_usd=3.0)
    assert bar2.remaining_usd is None


def test_signed_remaining_and_fraction() -> None:
    bar = compute_usage_bar(daily_cap_usd=10.0, spent_usd=3.0)
    assert bar.remaining_usd == 7.0
    assert bar.over_budget is False
    assert bar.fraction_used == 0.3

    over = compute_usage_bar(daily_cap_usd=5.0, spent_usd=8.0)
    assert over.remaining_usd == -3.0
    assert over.over_budget is True
    assert any("over display budget" in n for n in over.notes)


def test_would_exceed_null_when_remaining_unknown() -> None:
    bar = compute_usage_bar(daily_cap_usd=None, spent_usd=None)
    proj = project_prompt_against_bar(
        bar,
        projected_cost_usd_low=0.1,
        projected_cost_usd_high=0.2,
    )
    assert proj.would_exceed is None
    assert proj.remaining_after_high_usd is None
    assert any("remaining_usd unknown" in n for n in proj.notes)


def test_would_exceed_true_and_false() -> None:
    bar = compute_usage_bar(daily_cap_usd=1.0, spent_usd=0.5)
    over = project_prompt_against_bar(
        bar, projected_cost_usd_low=0.4, projected_cost_usd_high=0.6
    )
    assert over.would_exceed is True
    assert over.remaining_after_high_usd == pytest.approx(-0.1)

    ok = project_prompt_against_bar(
        bar, projected_cost_usd_low=0.1, projected_cost_usd_high=0.2
    )
    assert ok.would_exceed is False
    assert ok.remaining_after_high_usd == pytest.approx(0.3)


def test_http_project_route() -> None:
    app = FastAPI()
    register_model_usage_bar_routes(app)
    client = TestClient(app)
    r = client.post(
        "/settings/usage-bar/project",
        json={
            "daily_cap_usd": 10.0,
            "spent_usd": 2.0,
            "projected_cost_usd_low": 0.5,
            "projected_cost_usd_high": 1.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usage_bar"]["remaining_usd"] == 8.0
    assert body["prompt_projection"]["would_exceed"] is False
    # unknown remaining
    r2 = client.post(
        "/settings/usage-bar/project",
        json={
            "daily_cap_usd": None,
            "spent_usd": None,
            "projected_cost_usd_high": 1.0,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["usage_bar"]["remaining_usd"] is None
    assert r2.json()["prompt_projection"]["would_exceed"] is None


def test_http_rejects_nan_and_inf() -> None:
    app = FastAPI()
    register_model_usage_bar_routes(app)
    client = TestClient(app)
    for payload in (
        {"daily_cap_usd": "NaN", "spent_usd": 2.0, "projected_cost_usd_high": 1.0},
        {"daily_cap_usd": 10.0, "spent_usd": "Infinity"},
        {"daily_cap_usd": 10.0, "spent_usd": 1.0, "projected_cost_usd_high": "NaN"},
    ):
        r = client.post("/settings/usage-bar/project", json=payload)
        assert r.status_code == 422, (payload, r.text)


def test_pure_rejects_nan() -> None:
    with pytest.raises(ValueError, match="finite"):
        compute_usage_bar(daily_cap_usd=float("nan"), spent_usd=1.0)
