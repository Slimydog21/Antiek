"""Pure tests for Antiek-bench task model recommendation."""

from __future__ import annotations

from substrate.antiek_bench_task_model_recommendation_compose import (
    compose_antiek_bench_task_model_recommendation,
    format_antiek_bench_task_model_recommendation_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.3},
    {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
]


def _events():
    return [
        {
            "event_id": "e1",
            "task": "deep_research",
            "model_id": "gpt-5.5",
            "outcome": "worked",
            "score": 0.9,
        },
        {
            "event_id": "e2",
            "task": "deep_research",
            "model_id": "gpt-5.5",
            "outcome": "worked",
            "score": 0.85,
        },
        {
            "event_id": "e3",
            "task": "deep_research",
            "model_id": "mimo-v2",
            "outcome": "failed",
            "score": 0.2,
        },
        {
            "event_id": "e4",
            "task": "deep_research",
            "model_id": "mimo-v2",
            "outcome": "failed",
            "score": 0.3,
        },
        {
            "event_id": "e5",
            "task": "twin_notes",
            "model_id": "grok-4.5",
            "outcome": "worked",
            "score": 0.8,
        },
        {
            "event_id": "e6",
            "task": "twin_notes",
            "model_id": "grok-4.5",
            "outcome": "worked",
            "score": 0.75,
        },
    ]


def test_recommends_best_model():
    c = compose_antiek_bench_task_model_recommendation(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=5,
        projected_cost_usd_high=0.5,
        operator_ack=True,
        existing_tasks=["deep_research", "twin_notes"],
    )
    assert c.recommendation is not None
    assert c.recommendation.recommended_model_id == "gpt-5.5"
    assert c.decision_tree.driver.decision.selected_model_id == "gpt-5.5"
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.backlog_mutated is False
    assert "live_router_authorized=false" in format_antiek_bench_task_model_recommendation_summary(
        c
    )
    assert c.to_dict()["live_router_authorized"] is False


def test_explicit_selection_wins():
    c = compose_antiek_bench_task_model_recommendation(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        selected_model_id="mimo-v2",
        daily_cap_usd=20,
        spent_usd=5,
        operator_ack=True,
    )
    assert c.recommendation is not None
    assert c.recommendation.recommended_model_id == "gpt-5.5"
    assert c.decision_tree.driver.decision.selected_model_id == "mimo-v2"
    assert c.live_router_authorized is False


def test_insufficient_events_null_rec():
    c = compose_antiek_bench_task_model_recommendation(
        week_id="2026-W28",
        focus_task="deep_research",
        events=[
            {
                "event_id": "e1",
                "task": "deep_research",
                "model_id": "gpt-5.5",
                "outcome": "worked",
                "score": 0.9,
            }
        ],
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=1,
        operator_ack=True,
        min_events_for_recommendation=2,
    )
    assert c.recommendation is None
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False


def test_ack_false_blocks():
    c = compose_antiek_bench_task_model_recommendation(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=5,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False


def test_budget_would_exceed():
    c = compose_antiek_bench_task_model_recommendation(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        operator_ack=True,
    )
    assert c.decision_tree.would_exceed is True
    assert c.live_router_authorized is False
    assert c.live_meter_read is False
