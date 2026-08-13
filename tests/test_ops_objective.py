"""Own Your Mind P0 C1a — the objective-card endpoint.

``GET /ops/objective-card`` renders the live decision surfaces read from
the code/config that own them. These tests assert the card tracks the
SOURCES (not a frozen snapshot): every value is compared against the
module/config it claims to render, so a drift in either direction reds.

Covered surfaces: dispatch config (role_tiers / tiers with pricing /
tier_defaults), gap scoring constants + daemon spawn params, retrieval
gates, quality-gate thresholds, budget caps, and the reuse-gate
groundedness threshold.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def client() -> TestClient:
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False)
    )


def _card(client: TestClient) -> dict:
    r = client.get("/ops/objective-card")
    assert r.status_code == 200, r.text
    return r.json()


# ── dispatch ───────────────────────────────────────────────────────────────


def test_objective_card_dispatch_matches_config_yaml(client):
    card = _card(client)
    dispatch = card["dispatch"]
    assert dispatch["source"] == "substrate/dispatch/config.yaml"
    # role_tiers + tier_defaults come straight from the config.
    assert "decomposer" in dispatch["role_tiers"]
    assert dispatch["role_tiers"]["decomposer"] == "pro"
    assert dispatch["role_tiers"]["synthesizer"] == "synthesis"
    assert "flash" in dispatch["tier_defaults"]
    assert "pro" in dispatch["tier_defaults"]
    assert "synthesis" in dispatch["tier_defaults"]
    assert "verify" in dispatch["tier_defaults"]
    # Every tier carries provider + model + pricing fields.
    for tier_name in ("flash", "pro", "synthesis", "verify"):
        tier = dispatch["tiers"][tier_name]
        assert tier["provider"]
        assert tier["model"]
        pricing = tier["pricing"]
        for key in ("input_per_mtok", "output_per_mtok", "cached_input_per_mtok"):
            assert key in pricing, f"{tier_name}.pricing missing {key}"
    # cost_tracking section present.
    assert dispatch["cost_tracking"]["enabled"] is True


def test_objective_card_notes_placeholder_pricing(client):
    """config.yaml's own convention: 0.0 = unverified placeholder. The card
    must say so instead of reporting 'free'."""
    card = _card(client)
    dispatch = card["dispatch"]
    assert "pricing_placeholder" in dispatch
    assert "pricing_note" in dispatch
    # Every tier that HAS a pricing block carries numeric values (0.0
    # placeholder today). The deferred ``local`` tier declares no pricing
    # block at all — its absence is the config's own shape, respected.
    priced_tiers = [t for t in dispatch["tiers"].values() if "pricing" in t]
    assert priced_tiers, "expected at least one tier with a pricing block"
    for tier in priced_tiers:
        assert set(tier["pricing"]) == {
            "input_per_mtok", "output_per_mtok", "cached_input_per_mtok",
        }
        for value in tier["pricing"].values():
            assert isinstance(value, (int, float))


# ── gap scoring ────────────────────────────────────────────────────────────


def test_objective_card_gap_scoring_matches_scoring_module(client):
    from orchestration.continuous.scoring import (
        CO_OCCURRENCE_CAP,
        INTERACTION_BOOST,
        MAX_CHASE_COUNT,
        RECENCY_HALF_LIFE_DAYS,
    )

    constants = _card(client)["gap_scoring"]["constants"]
    assert constants == {
        "MAX_CHASE_COUNT": MAX_CHASE_COUNT,
        "RECENCY_HALF_LIFE_DAYS": RECENCY_HALF_LIFE_DAYS,
        "CO_OCCURRENCE_CAP": CO_OCCURRENCE_CAP,
        "INTERACTION_BOOST": INTERACTION_BOOST,
    }


def test_objective_card_daemon_spawn_params_match_daemon_defaults(client):
    from orchestration.continuous.daemon import DaemonConfig

    spawn = _card(client)["gap_scoring"]["daemon_spawn_params"]
    defaults = DaemonConfig()
    assert spawn == {
        "expected_cost_per_spawn_usd": defaults.expected_cost_per_spawn_usd,
        "max_spawns_per_iteration": defaults.max_spawns_per_iteration,
        "min_score_to_spawn": defaults.min_score_to_spawn,
        "spawn_policy_id": defaults.spawn_policy_id,
        "sleep_seconds": defaults.sleep_seconds,
    }


# ── retrieval gates ────────────────────────────────────────────────────────


def test_objective_card_retrieval_gates_match_gate_module(client):
    from substrate.graph.retrieval_gate import (
        PERSONAL_ONLY_CONTENT_CLASSES,
        PRIVILEGED_POLICY_TAGS,
        RESTRICTED_CONTENT_CLASSES,
    )

    gates = _card(client)["retrieval_gates"]
    assert gates["policy"] == "deny_by_default"
    assert set(gates["privileged_policy_tags"]) == PRIVILEGED_POLICY_TAGS
    assert set(gates["restricted_content_classes"]) == RESTRICTED_CONTENT_CLASSES
    assert set(gates["personal_only_content_classes"]) == PERSONAL_ONLY_CONTENT_CLASSES
    assert set(gates["non_privileged_excluded_content_classes"]) == (
        RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
    )


# ── quality gate ───────────────────────────────────────────────────────────


def test_objective_card_quality_gate_thresholds(client):
    import inspect

    from substrate.quality_gate.checks import SourceTierBounds, check_voice_style

    checks = _card(client)["quality_gate"]["checks"]
    voice_threshold = inspect.signature(check_voice_style).parameters[
        "threshold"
    ].default
    assert checks["voice_style"]["threshold"] == voice_threshold
    assert checks["voice_style"]["threshold"] == pytest.approx(0.70)
    bounds = SourceTierBounds()
    assert checks["source_tier"]["min_acceptable"] == bounds.min_acceptable
    assert checks["source_tier"]["max_acceptable"] == bounds.max_acceptable
    assert checks["source_tier"]["max_acceptable"] == 3
    assert checks["verification"]["rule"]
    assert checks["extraction_quality"]["min_distinct_chars"] >= 1


# ── budgets ────────────────────────────────────────────────────────────────


def test_objective_card_budgets_match_budget_modules(client):
    from orchestration.continuous import budget as continuous_budget
    from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD

    budgets = _card(client)["budgets"]
    assert budgets["research_runner"]["aggregate_cap_usd"] == (
        TOTAL_ACQUISITION_BUDGET_USD
    )
    daemon = budgets["continuous_daemon"]
    assert daemon["per_investigation_cap_usd"] == (
        continuous_budget.PER_INVESTIGATION_CAP_USD
    )
    assert daemon["default_daily_cap_usd"] == continuous_budget.DEFAULT_DAILY_CAP_USD
    assert daemon["max_topic_depth"] == continuous_budget.MAX_TOPIC_DEPTH
    assert daemon["daily_cap_env_override"] == "ANTIEK_DAEMON_HOURLY_BUDGET_USD"


# ── reuse gate ─────────────────────────────────────────────────────────────


def test_objective_card_reuse_gate_threshold(client):
    from substrate.flywheel.reuse_gate import REUSE_GROUNDEDNESS_THRESHOLD

    reuse = _card(client)["reuse_gate"]
    assert reuse["groundedness_threshold"] == REUSE_GROUNDEDNESS_THRESHOLD
    assert reuse["env_override"] == "REUSE_GROUNDEDNESS_THRESHOLD"


def test_objective_card_top_level_shape(client):
    card = _card(client)
    assert set(card) == {
        "generated_at",
        "dispatch",
        "gap_scoring",
        "retrieval_gates",
        "quality_gate",
        "budgets",
        "reuse_gate",
    }
    assert card["generated_at"]
