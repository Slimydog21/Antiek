"""substrate/trust_center/ tests.

Locks in:
- Default registry has the three baseline surfaces matching the
  previously-hardcoded /trust-center contract.
- A newly registered surface appears in build_publication() output
  (the React PrivacyDashboard's documented expectation).
- Builder accepts injected registry + loop_3 status for tests.
- reset_default_registry() works for test isolation.
- compliance_frameworks / substrate_controls overrides flow through.
"""

from __future__ import annotations

import pytest

from substrate.dp_shuffler import (
    EpsilonRegistry,
    EpsilonRegistryError,
    SurfaceConfig,
)
from substrate.trust_center import (
    DEFAULT_DELETION_SLA_DAYS,
    build_publication,
    default_registry,
    list_surface_descriptions,
    reset_default_registry,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    """Every test starts with the baseline."""
    reset_default_registry()
    yield
    reset_default_registry()


# ── Default baseline ──────────────────────────────────────────────


def test_default_registry_has_three_baseline_surfaces():
    reg = default_registry()
    names = {s.surface_name for s in reg.list_surfaces()}
    assert names == {
        "skill_invocation_frequency",
        "source_tier_preference_signals",
        "query_content_telemetry",
    }


def test_default_registry_baseline_matches_prior_hardcoded_values():
    """The endpoint used to hardcode these — Sprint 22 swap must not
    change the published contract for existing surfaces."""
    reg = default_registry()
    budgets = {s.surface_name: s.epsilon_per_day for s in reg.list_surfaces()}
    assert budgets["skill_invocation_frequency"] == 2.0
    assert budgets["source_tier_preference_signals"] == 1.0
    assert budgets["query_content_telemetry"] == 0.0


def test_default_registry_is_singleton():
    """Two calls return the same registry; mutations persist."""
    r1 = default_registry()
    r2 = default_registry()
    assert r1 is r2


def test_reset_default_registry_drops_extras():
    reg = default_registry()
    reg.register(SurfaceConfig(
        surface_name="custom_surface",
        epsilon_per_day=0.5,
        sensitivity="high",
        description="for test",
        opt_in_required=True,
    ))
    assert any(s.surface_name == "custom_surface" for s in reg.list_surfaces())
    reset_default_registry()
    assert not any(s.surface_name == "custom_surface" for s in default_registry().list_surfaces())


# ── Publication assembly ─────────────────────────────────────────


def test_build_publication_includes_baseline_budgets():
    payload = build_publication()
    assert payload.differential_privacy_epsilon_budgets == {
        "skill_invocation_frequency": 2.0,
        "source_tier_preference_signals": 1.0,
        "query_content_telemetry": 0.0,
    }
    assert payload.deletion_sla_days == DEFAULT_DELETION_SLA_DAYS == 30


def test_newly_registered_surface_appears_in_publication():
    """The React contract: any surface that registers with the
    registry appears in /trust-center automatically."""
    reg = default_registry()
    reg.register(SurfaceConfig(
        surface_name="dispatch_tier_telemetry",
        epsilon_per_day=0.5,
        sensitivity="high",
        description="dispatch tier hint sampling",
        opt_in_required=True,
    ))
    payload = build_publication()
    assert "dispatch_tier_telemetry" in payload.differential_privacy_epsilon_budgets
    assert payload.differential_privacy_epsilon_budgets["dispatch_tier_telemetry"] == 0.5


def test_build_publication_accepts_isolated_registry():
    """Tests + admin tools can pass their own registry."""
    custom = EpsilonRegistry()
    custom.register(SurfaceConfig(
        surface_name="only_one",
        epsilon_per_day=0.1,
        sensitivity="high",
        description="single-surface registry",
        opt_in_required=True,
    ))
    payload = build_publication(registry=custom)
    assert payload.differential_privacy_epsilon_budgets == {"only_one": 0.1}


def test_build_publication_loop_3_status_passes_through():
    payload = build_publication(loop_3_unlock_status={
        "trajectory_volume": True,
        "sft_readiness": True,
        "validated_reward": False,
        "open_weight_justification": False,
        "eval_headroom": False,
    })
    assert payload.loop_3_unlock_status["trajectory_volume"] is True
    assert payload.loop_3_unlock_status["validated_reward"] is False


def test_build_publication_compliance_overrides():
    payload = build_publication(
        compliance_frameworks=("ISO 27001",),
        substrate_controls=("custom control",),
    )
    assert payload.compliance_frameworks == ("ISO 27001",)
    assert payload.substrate_controls == ("custom control",)


def test_build_publication_default_compliance_includes_dp_cap():
    payload = build_publication()
    # The §16.2 hard cap on ε must always be in the compliance section.
    assert any("ε ≤ 10" in c or "epsilon" in c.lower() for c in payload.compliance_frameworks)


# ── as_dict integration shape ────────────────────────────────────


def test_payload_as_dict_matches_endpoint_contract():
    payload = build_publication()
    d = payload.as_dict()
    # The keys that the React frontend reads.
    expected_keys = {
        "differential_privacy_epsilon_budgets",
        "deletion_sla_days",
        "substrate_controls",
        "compliance_frameworks",
        "loop_3_unlock_status",
    }
    assert set(d.keys()) == expected_keys
    assert isinstance(d["differential_privacy_epsilon_budgets"], dict)
    assert isinstance(d["substrate_controls"], list)
    assert isinstance(d["compliance_frameworks"], list)


# ── list_surface_descriptions ────────────────────────────────────


def test_list_surface_descriptions_includes_metadata():
    descriptions = list_surface_descriptions()
    by_name = {d["surface_name"]: d for d in descriptions}
    assert "skill_invocation_frequency" in by_name
    assert by_name["skill_invocation_frequency"]["sensitivity"] == "low"
    assert by_name["query_content_telemetry"]["sensitivity"] == "forbidden"


# ── §16.2 cap respected for new registrations ────────────────────


def test_cannot_register_surface_over_max_epsilon():
    """A new surface that violates ε ≤ 10 is rejected by the
    underlying registry; build_publication never publishes it."""
    reg = default_registry()
    with pytest.raises(EpsilonRegistryError):
        reg.register(SurfaceConfig(
            surface_name="bad_surface",
            epsilon_per_day=999.0,
            sensitivity="low",  # cap at 4.0 — 999 exceeds it
            description="violates the cap",
            opt_in_required=False,
        ))
    payload = build_publication()
    assert "bad_surface" not in payload.differential_privacy_epsilon_budgets
