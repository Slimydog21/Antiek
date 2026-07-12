"""Pure tests for settings add-model + bench decision compose."""

from __future__ import annotations

from substrate.settings_add_model_bench_decision_compose import (
    compose_settings_add_model_bench_decision,
    format_settings_add_model_bench_decision_summary,
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


def test_add_model_bench_ready():
    c = compose_settings_add_model_bench_decision(
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
        existing_tasks=["deep_research"],
    )
    assert c.add_model.pack_ready is True
    assert c.bench_rec.pack_ready is True
    assert c.pack_ready is True
    assert c.bench_rec.recommendation is not None
    assert c.bench_rec.recommendation.recommended_model_id == "gpt-5.5"
    assert c.bench_rec.decision_tree.would_exceed is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert (
        c.authority == "settings_add_model_bench_decision_compose_advisory"
    )
    assert "live_router_authorized=false" in format_settings_add_model_bench_decision_summary(
        c
    )


def test_would_exceed_projection():
    c = compose_settings_add_model_bench_decision(
        models=MODELS,
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        operator_ack=True,
    )
    assert c.bench_rec.decision_tree.would_exceed is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False


def test_operator_ack_false():
    c = compose_settings_add_model_bench_decision(
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
    )
    assert c.pack_ready is False
    assert c.inventory_mutated is False


def test_propose_add_with_bench():
    c = compose_settings_add_model_bench_decision(
        models=[{"model_id": "gpt-5.5"}],
        pending_add_model_ids=["mimo-v2"],
        action="propose_add",
        week_id="2026-W28",
        focus_task="deep_research",
        events=events_deep_research(),
        decision_models=DECISION_MODELS,
        daily_cap_usd=15,
        spent_usd=2,
        projected_cost_usd_high=0.3,
        operator_ack=True,
    )
    assert c.add_model.proposed_new_count == 1
    assert c.add_model.pack_ready is True
    assert c.bench_rec.pack_ready is True
    assert c.pack_ready is True
    assert c.inventory_mutated is False
