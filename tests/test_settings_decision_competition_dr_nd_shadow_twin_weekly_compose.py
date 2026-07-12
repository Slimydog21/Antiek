"""Pure tests for settings decision over competition DR ND shadow twin weekly."""

from __future__ import annotations

from substrate.settings_decision_competition_dr_nd_shadow_twin_weekly_compose import (
    compose_settings_decision_competition_dr_nd_shadow_twin_weekly,
    format_settings_decision_competition_dr_nd_shadow_twin_weekly_summary,
)
from tests.test_competition_dr_nd_shadow_twin_presentation_weekly_compose import (
    COMPETITION,
    ND_PACK,
)
from tests.test_settings_add_model_bench_decision_compose import (
    DECISION_MODELS,
    MODELS,
    events_deep_research,
)

SETTINGS = {
    "models": MODELS,
    "pending_add_model_ids": ["mimo-v2"],
    "action": "preview",
    "week_id": "2026-W28",
    "focus_task": "deep_research",
    "events": events_deep_research(),
    "decision_models": DECISION_MODELS,
    "selected_model_id": "gpt-5.5",
    "daily_cap_usd": 20,
    "spent_usd": 5,
    "projected_cost_usd_high": 0.5,
    "projected_cost_usd_low": 0.2,
    "existing_tasks": ["deep_research", "twin_notes"],
}

COMPETITION_PACK = {
    "competition": COMPETITION,
    "nd_pack": ND_PACK,
}


def test_settings_decision_competition_pack_ready():
    c = compose_settings_decision_competition_dr_nd_shadow_twin_weekly(
        settings=SETTINGS,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.competition_pack.pack_ready is True
    assert c.week_aligned is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "settings_decision_competition_dr_nd_shadow_twin_weekly_compose_advisory"
    )
    assert "secrets_stored=false" in (
        format_settings_decision_competition_dr_nd_shadow_twin_weekly_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_decision_competition_dr_nd_shadow_twin_weekly(
        settings=SETTINGS,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_week_mismatch_blocks():
    c = compose_settings_decision_competition_dr_nd_shadow_twin_weekly(
        settings={**SETTINGS, "week_id": "2026-W99"},
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.week_aligned is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_budget_projection_would_exceed_advisory():
    c = compose_settings_decision_competition_dr_nd_shadow_twin_weekly(
        settings={
            **SETTINGS,
            "daily_cap_usd": 1,
            "spent_usd": 0.9,
            "projected_cost_usd_high": 0.5,
        },
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.settings.bench_rec.decision_tree.would_exceed is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert c.competition_pack.pack_ready is True
