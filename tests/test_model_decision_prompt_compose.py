"""Hermetic tests for pure model decision prompt compose."""

from __future__ import annotations

import pytest

from substrate.model_decision.prompt_compose import (
    ModelDecisionPromptComposeError,
    compose_model_decision_with_projection,
)

MODELS = [
    {
        "model_id": "flash-1",
        "tier": "flash",
        "projected_cost_usd_low": 0.1,
        "projected_cost_usd_high": 0.5,
    },
    {
        "model_id": "pro-1",
        "tier": "pro",
        "projected_cost_usd_low": 1.0,
        "projected_cost_usd_high": 3.0,
    },
]


def test_exceed_when_high_gt_remaining() -> None:
    r = compose_model_decision_with_projection(
        selected_model_id="pro-1",
        models=MODELS,
        daily_cap_usd=10.0,
        spent_usd=8.0,
    )
    assert r.would_exceed is True
    assert r.selected_tier == "pro"
    assert r.to_dict()["authority"] == "model_decision_prompt_compose_advisory"


def test_null_when_remaining_unknown() -> None:
    r = compose_model_decision_with_projection(
        selected_model_id="flash-1",
        models=MODELS,
        daily_cap_usd=None,
        spent_usd=None,
    )
    assert r.would_exceed is None
    assert r.bar.remaining_usd is None


def test_null_when_high_unknown() -> None:
    r = compose_model_decision_with_projection(
        selected_model_id="flash-1",
        models=[{"model_id": "flash-1", "tier": "flash"}],
        daily_cap_usd=10.0,
        spent_usd=1.0,
    )
    assert r.would_exceed is None


def test_rejects_unknown_model() -> None:
    with pytest.raises(ModelDecisionPromptComposeError, match="not found"):
        compose_model_decision_with_projection(
            selected_model_id="missing",
            models=MODELS,
            daily_cap_usd=10.0,
            spent_usd=1.0,
        )


def test_input_override() -> None:
    r = compose_model_decision_with_projection(
        selected_model_id="flash-1",
        models=MODELS,
        daily_cap_usd=10.0,
        spent_usd=9.0,
        projected_cost_usd_high=0.5,
        projected_cost_usd_low=0.1,
        use_model_cost_defaults=False,
    )
    assert r.would_exceed is False
