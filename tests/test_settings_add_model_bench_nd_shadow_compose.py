"""Pure tests for settings add-model bench ND shadow compose."""

from __future__ import annotations

from substrate.settings_add_model_bench_nd_shadow_compose import (
    compose_settings_add_model_bench_nd_shadow,
    format_settings_add_model_bench_nd_shadow_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "provider": "openai"},
    {"model_id": "grok-4.5", "provider": "xai"},
]
DECISION_MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.3},
    {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
]


def events_deep_research():
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
    ]


def test_settings_nd_shadow_ready_reject():
    c = compose_settings_add_model_bench_nd_shadow(
        models=MODELS,
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=20,
        spent_usd=5,
        projected_cost_usd_high=0.5,
        operator_ack=True,
        nd_recommended_model_id="gpt-5.5",
        kill_switch_on=False,
        nd_confidence=0.7,
        existing_tasks=["deep_research"],
    )
    assert c.settings_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.bench_vs_nd == "agree"
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert (
        c.authority == "settings_add_model_bench_nd_shadow_compose_advisory"
    )
    assert "production_router_verdict=REJECT" in format_settings_add_model_bench_nd_shadow_summary(
        c
    )


def test_kill_switch_hides_nd():
    c = compose_settings_add_model_bench_nd_shadow(
        models=MODELS,
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=20,
        spent_usd=5,
        operator_ack=True,
        nd_recommended_model_id="mimo-v2",
        kill_switch_on=True,
    )
    assert c.bench_vs_nd == "nd_hidden"
    assert c.nd_shadow.shadow_visible is False
    assert c.production_router_verdict == "REJECT"
    assert c.pack_ready is True


def test_bench_vs_nd_disagree():
    c = compose_settings_add_model_bench_nd_shadow(
        models=MODELS,
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=20,
        spent_usd=5,
        operator_ack=True,
        nd_recommended_model_id="mimo-v2",
        kill_switch_on=False,
    )
    assert c.bench_vs_nd == "disagree"
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert c.operator_selected_model_id != "mimo-v2"


def test_operator_ack_false():
    c = compose_settings_add_model_bench_nd_shadow(
        models=MODELS,
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=20,
        spent_usd=1,
        operator_ack=False,
        nd_recommended_model_id="gpt-5.5",
        kill_switch_on=False,
    )
    assert c.pack_ready is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"
