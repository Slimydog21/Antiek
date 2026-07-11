"""Pure tests for NotDiamond + bench decision shadow compose."""

from __future__ import annotations

from substrate.notdiamond_bench_decision_shadow_compose import (
    compose_notdiamond_bench_decision_shadow,
    format_notdiamond_bench_decision_shadow_summary,
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
            "score": 0.88,
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
            "score": 0.25,
        },
    ]


def test_agree():
    c = compose_notdiamond_bench_decision_shadow(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=4,
        projected_cost_usd_high=0.5,
        nd_recommended_model_id="gpt-5.5",
        kill_switch_on=False,
        nd_confidence=0.8,
        operator_ack=True,
    )
    assert c.bench_rec.recommendation is not None
    assert c.bench_rec.recommendation.recommended_model_id == "gpt-5.5"
    assert c.nd_shadow.shadow_visible is True
    assert c.bench_vs_nd == "agree"
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.pack_ready is True
    assert "production_router_verdict=REJECT" in format_notdiamond_bench_decision_shadow_summary(
        c
    )


def test_kill_switch():
    c = compose_notdiamond_bench_decision_shadow(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=4,
        nd_recommended_model_id="mimo-v2",
        kill_switch_on=True,
        operator_ack=True,
    )
    assert c.nd_shadow.shadow_visible is False
    assert c.bench_vs_nd == "nd_hidden"
    assert c.production_router_verdict == "REJECT"


def test_disagree():
    c = compose_notdiamond_bench_decision_shadow(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=4,
        nd_recommended_model_id="mimo-v2",
        kill_switch_on=False,
        operator_ack=True,
    )
    assert c.bench_vs_nd == "disagree"
    assert c.operator_selected_model_id == "gpt-5.5"
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_explicit_selection():
    c = compose_notdiamond_bench_decision_shadow(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        selected_model_id="grok-4.5",
        daily_cap_usd=20,
        spent_usd=4,
        nd_recommended_model_id="gpt-5.5",
        kill_switch_on=False,
        operator_ack=True,
    )
    assert c.operator_selected_model_id == "grok-4.5"
    assert c.live_router_authorized is False


def test_ack_false():
    c = compose_notdiamond_bench_decision_shadow(
        week_id="2026-W28",
        focus_task="deep_research",
        events=_events(),
        models=MODELS,
        daily_cap_usd=20,
        spent_usd=4,
        nd_recommended_model_id="gpt-5.5",
        kill_switch_on=False,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.production_router_verdict == "REJECT"
