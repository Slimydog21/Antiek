"""Red-proofs: advisory model decision tree + HTTP rank route."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.model_decision_routes import (
    register_model_decision_routes,
)
from substrate.model_decision.tree import (
    AUTHORITY,
    ModelCandidate,
    rank_models_for_task,
)


def test_authority_is_always_advisory() -> None:
    r = rank_models_for_task(
        "deep_research",
        [ModelCandidate("m1", tier="reasoning")],
    )
    assert r.authority == AUTHORITY == "advisory"


def test_empty_inventory_recommends_none() -> None:
    r = rank_models_for_task("general", [])
    assert r.recommended_model_id is None
    assert r.ranked == []


def test_disabled_models_omitted() -> None:
    r = rank_models_for_task(
        "note_taker",
        [
            ModelCandidate("slow", tier="reasoning", enabled=False),
            ModelCandidate("fast", tier="flash", enabled=True),
        ],
    )
    assert r.recommended_model_id == "fast"
    assert [x.model_id for x in r.ranked] == ["fast"]


def test_deep_research_prefers_reasoning_without_bench() -> None:
    r = rank_models_for_task(
        "deep_research",
        [
            ModelCandidate("flashy", tier="flash"),
            ModelCandidate("thinker", tier="reasoning"),
            ModelCandidate("mid", tier="balanced"),
        ],
    )
    assert r.recommended_model_id == "thinker"
    assert r.ranked[0].score > r.ranked[-1].score


def test_note_taker_prefers_flash() -> None:
    r = rank_models_for_task(
        "note_taker",
        [
            ModelCandidate("thinker", tier="reasoning"),
            ModelCandidate("flashy", tier="flash"),
        ],
    )
    assert r.recommended_model_id == "flashy"


def test_bench_scores_override_static_affinity() -> None:
    r = rank_models_for_task(
        "deep_research",
        [
            ModelCandidate("thinker", tier="reasoning"),
            ModelCandidate("underdog", tier="flash"),
        ],
        bench_scores={"deep_research": {"underdog": 0.99, "thinker": 0.1}},
    )
    assert r.recommended_model_id == "underdog"
    assert "antiek-bench" in r.ranked[0].rationale


def test_would_exceed_null_when_remaining_unknown() -> None:
    r = rank_models_for_task(
        "general",
        [ModelCandidate("m", tier="balanced", usd_per_1k_tokens=1.0)],
        prompt_chars=4000,
        remaining_usd=None,
    )
    assert r.ranked[0].would_exceed is None
    assert r.ranked[0].projected_cost_usd_high is not None
    assert any("would_exceed is null" in n for n in r.notes)


def test_would_exceed_true_when_projection_above_remaining() -> None:
    # 4000 chars → 1000 tokens; with output band mid ~2000 tokens total → $2 at $1/1k
    r = rank_models_for_task(
        "general",
        [ModelCandidate("pricey", tier="balanced", usd_per_1k_tokens=1.0)],
        prompt_chars=4000,
        remaining_usd=0.01,
    )
    assert r.ranked[0].would_exceed is True
    assert r.ranked[0].projected_cost_usd_high is not None
    assert r.ranked[0].projected_cost_usd_high > 0.01


def test_would_exceed_false_when_within_budget() -> None:
    r = rank_models_for_task(
        "general",
        [ModelCandidate("cheap", tier="flash", usd_per_1k_tokens=0.001)],
        prompt_chars=100,
        remaining_usd=10.0,
    )
    assert r.ranked[0].would_exceed is False


def test_unknown_task_falls_back_to_general() -> None:
    r = rank_models_for_task(
        "totally_unknown_task",
        [ModelCandidate("m", tier="balanced")],
    )
    assert r.task == "general"


def test_http_rank_route_advisory_and_projection() -> None:
    app = FastAPI()
    register_model_decision_routes(app)
    client = TestClient(app)
    resp = client.post(
        "/settings/model-decision/rank",
        json={
            "task": "deep_research",
            "remaining_usd": 0.5,
            "prompt_chars": 8000,
            "models": [
                {
                    "model_id": "opus-class",
                    "provider": "anthropic",
                    "tier": "reasoning",
                    "usd_per_1k_tokens": 0.015,
                },
                {
                    "model_id": "flash-class",
                    "provider": "x",
                    "tier": "flash",
                    "usd_per_1k_tokens": 0.001,
                },
            ],
            "bench_scores": {
                "deep_research": {"opus-class": 0.9, "flash-class": 0.5}
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authority"] == "advisory"
    assert body["recommended_model_id"] == "opus-class"
    assert body["ranked"][0]["would_exceed"] in (True, False)
    # Must not invent a zero remaining when not sent
    assert body["remaining_usd"] == 0.5


def test_http_no_remaining_null_would_exceed() -> None:
    app = FastAPI()
    register_model_decision_routes(app)
    client = TestClient(app)
    resp = client.post(
        "/settings/model-decision/rank",
        json={
            "task": "reading",
            "models": [{"model_id": "a", "tier": "flash", "usd_per_1k_tokens": 0.01}],
            "prompt_chars": 1000,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["remaining_usd"] is None
    assert body["ranked"][0]["would_exceed"] is None
