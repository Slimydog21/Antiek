"""Hermetic tests for settings model driver tab compose."""

from __future__ import annotations

import pytest

from substrate.settings_model_driver_tab_compose import (
    SettingsModelDriverTabComposeError,
    compose_settings_model_driver_tab,
)

MODELS = [
    {
        "model_id": "flash-1",
        "tier": "flash",
        "projected_cost_usd_high": 0.5,
        "projected_cost_usd_low": 0.1,
    },
    {
        "model_id": "pro-1",
        "tier": "pro",
        "projected_cost_usd_high": 3,
        "projected_cost_usd_low": 1,
    },
]


def test_compose_without_router_or_secrets() -> None:
    t = compose_settings_model_driver_tab(
        selected_model_id="flash-1",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=2,
        bench_bests=[
            {"task": "deep_research", "best_model_id": "pro-1", "score": 0.9}
        ],
        focus_task="deep_research",
        nd_shadow={
            "recommended_model_id": "pro-1",
            "kill_switch_on": False,
            "confidence": 0.7,
        },
        pending_add_model_ids=["local-llama"],
    )
    assert t.live_router_authorized is False
    assert t.secrets_stored is False
    assert t.to_dict()["live_router_authorized"] is False
    assert t.to_dict()["secrets_stored"] is False
    assert t.tab_ready is True
    assert t.bench_aligned is False
    assert t.nd_shadow_differs is True
    assert t.pending_add_count == 1
    assert t.authority == "settings_model_driver_tab_compose_advisory"


def test_nd_kill_switch_suppresses() -> None:
    t = compose_settings_model_driver_tab(
        selected_model_id="flash-1",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=2,
        nd_shadow={
            "recommended_model_id": "pro-1",
            "kill_switch_on": True,
        },
    )
    assert t.nd_shadow_differs is None
    assert t.nd_shadow_model is None
    assert t.live_router_authorized is False


def test_rejects_secretish_pending() -> None:
    with pytest.raises(SettingsModelDriverTabComposeError, match="secret material"):
        compose_settings_model_driver_tab(
            selected_model_id="flash-1",
            models=MODELS,
            daily_cap_usd=None,
            spent_usd=None,
            pending_add_model_ids=["sk-abc123secret"],
        )


def test_bench_aligned() -> None:
    t = compose_settings_model_driver_tab(
        selected_model_id="pro-1",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=1,
        bench_bests=[
            {"task": "deep_research", "best_model_id": "pro-1", "score": 0.95}
        ],
        focus_task="deep_research",
    )
    assert t.bench_aligned is True
    assert t.secrets_stored is False


def test_would_exceed_null_unknown_costs() -> None:
    t = compose_settings_model_driver_tab(
        selected_model_id="flash-1",
        models=[{"model_id": "flash-1", "tier": "flash"}],
        daily_cap_usd=10,
        spent_usd=2,
    )
    assert t.decision.would_exceed is None
    assert t.live_router_authorized is False
