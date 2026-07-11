"""Pure tests for settings decision tree usage bar compose."""

from __future__ import annotations

import pytest

from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
    format_settings_decision_tree_usage_bar_summary,
)

MODELS = [
    {
        "model_id": "gpt-5",
        "tier": "frontier",
        "projected_cost_usd_high": 2,
        "projected_cost_usd_low": 1,
    },
    {"model_id": "composer-2.5", "tier": "workhorse", "projected_cost_usd_high": 0.5},
]


def test_decision_ready_usage_percent():
    c = compose_settings_decision_tree_usage_bar(
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=100,
        spent_usd=40,
        projected_cost_usd_high=2,
        projected_cost_usd_low=1,
        operator_ack=True,
    )
    assert c.decision_ready is True
    assert c.usage_percent == 40.0
    assert c.remaining_usd == 60.0
    assert c.would_exceed is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    s = format_settings_decision_tree_usage_bar_summary(c)
    assert "live_router_authorized=false" in s
    assert c.to_dict()["live_meter_read"] is False


def test_would_exceed_true():
    c = compose_settings_decision_tree_usage_bar(
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=9,
        projected_cost_usd_high=5,
        operator_ack=True,
    )
    assert c.would_exceed is True
    assert c.usage_percent == 90.0


def test_usage_null_when_cap_unknown():
    c = compose_settings_decision_tree_usage_bar(
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=None,
        spent_usd=5,
        projected_cost_usd_high=1,
        operator_ack=True,
    )
    assert c.usage_percent is None
    assert c.would_exceed is None
    assert c.decision_ready is True


def test_ack_false():
    c = compose_settings_decision_tree_usage_bar(
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=100,
        spent_usd=10,
        operator_ack=False,
    )
    assert c.decision_ready is False


def test_rejects_unknown_model():
    with pytest.raises(SettingsDecisionTreeUsageBarComposeError, match="not found"):
        compose_settings_decision_tree_usage_bar(
            selected_model_id="nope",
            models=MODELS,
            daily_cap_usd=10,
            spent_usd=1,
            operator_ack=True,
        )
