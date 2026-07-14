"""Tests for interfaces/research/api/composer_projection_routes.py — asks #8/#10 Slice B.

The route is a thin HTTP adapter over resolve_composer_projection (#2057 Slice A). These
tests verify the adapter: honest budget readout (shared Settings source), the real projector
path, schema hardening, and serialization.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.composer_projection_routes import (
    register_composer_projection_routes,
    set_composer_projection_budget_read,
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    register_composer_projection_routes(app)
    return TestClient(app)


def _budget(cap: float | None, spent: float | None) -> SimpleNamespace:
    """A fake read_operator_budget() return."""
    return SimpleNamespace(daily_cap_usd=cap, spent_usd=spent)


def _request(
    *,
    cap: float | None = 10.0,
    spent: float | None = 1.0,
    choice: dict | None = None,
    candidates: list[dict] | None = None,
) -> dict:
    cands = candidates if candidates is not None else [
        {
            "tier": "pro",
            "provider": "openai",
            "model": "gpt-pro",
            "ready": True,
            "estimated_usd_low": 0.10,
            "estimated_usd_high": 0.20,
            "would_exceed_budget": False,
            "benchmark_score": 0.9,
            "benchmark_samples": 50,
        },
        {
            "tier": "flash",
            "provider": "openai",
            "model": "gpt-flash",
            "ready": True,
            "estimated_usd_low": 0.01,
            "estimated_usd_high": 0.02,
            "would_exceed_budget": False,
        },
    ]
    return {
        "task": "deep_research",
        "candidates": cands,
        "bounded_usage": [{"unit": "input_token", "maximum": 1000}],
        "choice": choice,
    }


# ---------------------------------------------------------------------------
# honest budget readout — shared Settings source, None when unmeasurable
# ---------------------------------------------------------------------------


def test_budget_read_from_injected_source(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 3.0))
    try:
        res = client.post("/settings/composer-projection/resolve", json=_request())
        assert res.status_code == 200
        body = res.json()
        assert body["budget"]["daily_cap_usd"] == 10.0
        assert body["budget"]["spent_usd"] == 3.0
        assert body["remaining_usd"] == pytest.approx(7.0)
    finally:
        set_composer_projection_budget_read(None)


def test_unknown_spent_is_none_not_zero(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, None))
    try:
        res = client.post("/settings/composer-projection/resolve", json=_request())
        assert res.status_code == 200
        body = res.json()
        assert body["budget"]["spent_usd"] is None
        assert body["remaining_usd"] is None  # cap - None = None
        assert body["would_exceed_budget"] is None  # unmeasurable, never False
    finally:
        set_composer_projection_budget_read(None)


def test_no_cap_no_spent_all_none(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(None, None))
    try:
        res = client.post("/settings/composer-projection/resolve", json=_request())
        assert res.status_code == 200
        body = res.json()
        assert body["budget"]["daily_cap_usd"] is None
        assert body["would_exceed_budget"] is None
    finally:
        set_composer_projection_budget_read(None)


# ---------------------------------------------------------------------------
# advisory authority + serialization
# ---------------------------------------------------------------------------


def test_authority_advisory_and_ranked_serialized(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        res = client.post("/settings/composer-projection/resolve", json=_request())
        body = res.json()
        assert body["authority"] == "advisory_explanatory"
        assert len(body["ranked_candidates"]) == 2
        pro = next(c for c in body["ranked_candidates"] if c["model"] == "gpt-pro")
        assert pro["quality_basis"] == "measured"
        flash = next(c for c in body["ranked_candidates"] if c["model"] == "gpt-flash")
        assert flash["quality_basis"] == "static_prior"
        assert pro["pricing_status"] == "known"
    finally:
        set_composer_projection_budget_read(None)


def test_curated_default_when_no_choice(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        res = client.post("/settings/composer-projection/resolve", json=_request(choice=None))
        body = res.json()
        assert body["chosen_provider"] is None
        assert body["chosen_model"] is None
        assert body["chosen_projection"] is None
        assert any("curated default" in n for n in body["notes"])
    finally:
        set_composer_projection_budget_read(None)


def test_explicit_choice_with_projection(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        res = client.post(
            "/settings/composer-projection/resolve",
            json=_request(choice={"provider": "openai", "model": "gpt-pro"}),
        )
        body = res.json()
        assert body["chosen_provider"] == "openai"
        assert body["chosen_model"] == "gpt-pro"
        # The real projector resolves a projection (or withholds it if rates absent).
        # Either way the shape is honest — projection is present OR would_exceed is None.
        assert "chosen_projection" in body
        assert "would_exceed_budget" in body
    finally:
        set_composer_projection_budget_read(None)


# ---------------------------------------------------------------------------
# schema hardening
# ---------------------------------------------------------------------------


def test_extra_fields_rejected(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        payload = _request()
        payload["rogue_field"] = "inject"  # type: ignore[typeddict-unknown-key]
        res = client.post("/settings/composer-projection/resolve", json=payload)
        assert res.status_code == 422
    finally:
        set_composer_projection_budget_read(None)


def test_empty_candidates_rejected(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        res = client.post(
            "/settings/composer-projection/resolve",
            json=_request(candidates=[]),
        )
        assert res.status_code == 422  # min_length=1
    finally:
        set_composer_projection_budget_read(None)


def test_unknown_usage_unit_rejected(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        payload = _request()
        payload["bounded_usage"] = [{"unit": "gigawatt", "maximum": 1000}]
        res = client.post("/settings/composer-projection/resolve", json=payload)
        assert res.status_code == 422  # Literal rejects unknown unit
    finally:
        set_composer_projection_budget_read(None)


def test_negative_benchmark_score_rejected(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        cands = [
            {
                "tier": "pro",
                "provider": "openai",
                "model": "gpt-pro",
                "ready": True,
                "estimated_usd_low": 0.10,
                "estimated_usd_high": 0.20,
                "would_exceed_budget": False,
                "benchmark_score": -0.5,
            }
        ]
        res = client.post(
            "/settings/composer-projection/resolve",
            json=_request(candidates=cands),
        )
        assert res.status_code == 422  # ge=0.0
    finally:
        set_composer_projection_budget_read(None)


# ---------------------------------------------------------------------------
# ready-not-strict-bool would be a gap — verify strictness where present
# ---------------------------------------------------------------------------


def test_ready_must_be_bool(client: TestClient) -> None:
    set_composer_projection_budget_read(lambda: _budget(10.0, 1.0))
    try:
        cands = [
            {
                "tier": "pro",
                "provider": "openai",
                "model": "gpt-pro",
                "ready": "yes",  # type: ignore[dict-item]
                "estimated_usd_low": 0.10,
                "estimated_usd_high": 0.20,
                "would_exceed_budget": False,
            }
        ]
        res = client.post(
            "/settings/composer-projection/resolve",
            json=_request(candidates=cands),
        )
        assert res.status_code == 422
    finally:
        set_composer_projection_budget_read(None)
