"""Chaos test for the zai-primary (GLM-5.2) → OpenRouter-fallback chain.

Loads the **production** ``substrate/dispatch/config.yaml`` (not a
synthetic test config) and proves that when the Hermes bridge is
unreachable (operator's `volume over quality` posture in flames),
the substrate's OpenRouter fallback actually picks up the dispatch
for every primary tier.

This is the architectural insurance test for the Hermes-primary bet.
Without it, ``dispatch/config.yaml`` could quietly lose a fallback
(see the verify-tier defect surfaced while writing this file) and
no test would catch it until a real bridge outage took the substrate
dark.

What this test does NOT cover:
- Network-level behavior of the actual openrouter provider (unit-
  tested in ``test_dispatch.py`` via the OpenAI-compat shape).
- OAuth refresh / 429 behavior of the bridge itself (that's Hermes
  Agent's responsibility, lives in its repo per the stewardship
  boundary).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch import (  # noqa: E402
    register_provider,
    reset_provider_registry,
)
from substrate.dispatch.base import (
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
)
from substrate.dispatch.router import DispatchConfig, dispatch
from substrate.event_log import trajectory
from substrate.schemas import Event

# Sprint 17 dispatch tier measurement (master-spec §14.4, 2026-05-19):
# synthesis is inverted to OpenRouter-primary with Hermes fallback for
# the 2-week measurement window. flash, pro, verify stay Hermes-primary.
# All tiers retain exactly one fallback regardless of which family is
# primary (the chaos-test invariant is "always a fallback," not "always
# fall to OpenRouter").
ALL_TIERS_WITH_FALLBACK = ("flash", "pro", "synthesis", "verify")
ZAI_PRIMARY_TIERS = ("flash", "pro", "verify")  # GLM-5.2 driver; synthesis is opus-primary
OPENROUTER_PRIMARY_TIERS = ("synthesis",)  # Sprint 17-20 measurement window only
ROLES_ROUTED_TO_ZAI_PRIMARY = (
    "decomposer",          # pro
    "evidence_retriever",  # flash
    "verifier",            # verify
    "note_taker",          # flash
    "user_agent",          # pro
)
ROLES_ROUTED_TO_OPENROUTER_PRIMARY = (
    "synthesizer",         # synthesis (measurement window)
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def _events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return d


@pytest.fixture(scope="module")
def production_config() -> DispatchConfig:
    """Load the real ``substrate/dispatch/config.yaml``.

    Loaded once per test module since the YAML is static for the
    session — repeatedly parsing it would only add latency."""
    cfg_path = Path(__file__).resolve().parents[1] / "substrate" / "dispatch" / "config.yaml"
    return DispatchConfig.from_yaml(cfg_path)


# ─────────────────────────────────────────────────────────────────────
# Stub providers
# ─────────────────────────────────────────────────────────────────────


class _FailingZaiProvider:
    """Simulates the GLM-5.2 driver being down. Every call raises
    ProviderError, which is what Antiek's router needs to see in
    order to walk to ``tier.fallback``."""

    name = "zai"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        raise ProviderError(
            "simulated zai outage",
            provider=self.name,
            model=model,
            latency_ms=12,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        # Never reached, but the router calls this on the response
        # path. Returning zeros keeps the contract honest.
        return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)


class _WorkingOpenRouterProvider:
    """Stub stand-in for the openrouter provider used as fallback.
    Returns a realistic OpenAI-shape response so the router's usage
    normalization + dispatch.call event emission paths exercise
    correctly under the fallback case."""

    name = "openrouter"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        return RawProviderResponse(
            text="fallback response — bridge was down, openrouter handled it",
            raw_usage={
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "total_tokens": 130,
            },
            finish_reason="stop",
            latency_ms=420,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
            cached_input_tokens=0,
        )


class _FailingOpenRouterProvider:
    """Mirror of _FailingZaiProvider for the inverted case: when
    the synthesis tier (OpenRouter-primary during the Sprint 17-20
    measurement window) sees its primary die, the router walks to
    the zai (GLM-5.2) fallback."""

    name = "openrouter"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        raise ProviderError(
            "simulated openrouter outage",
            provider=self.name,
            model=model,
            latency_ms=12,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)


class _WorkingZaiProvider:
    """Mirror of _WorkingOpenRouterProvider for the inverted case.
    Returns a realistic GLM-5.2 response (zai driver) so the
    router's usage normalization + dispatch.call emission paths
    exercise correctly under the synthesis-fallback case."""

    name = "zai"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        return RawProviderResponse(
            text="zai fallback — openrouter was down, glm-5.2 handled it",
            raw_usage={
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "total_tokens": 130,
            },
            finish_reason="stop",
            latency_ms=380,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
            cached_input_tokens=0,
        )


# ─────────────────────────────────────────────────────────────────────
# 1. Config-level invariants (architectural insurance)
# ─────────────────────────────────────────────────────────────────────


def test_every_primary_tier_has_a_fallback(production_config):
    """The chain only works if every primary tier carries a fallback —
    regardless of which family is primary (Hermes for flash/pro/verify,
    OpenRouter for synthesis during the Sprint 17-20 measurement
    window). A tier without a fallback is a substrate-dark hazard the
    moment its primary fails."""
    missing_fallbacks: list[str] = []
    for tier_name in ALL_TIERS_WITH_FALLBACK:
        tier = production_config.tiers.get(tier_name)
        assert tier is not None, f"missing tier {tier_name!r}"
        if tier.fallback is None:
            missing_fallbacks.append(tier_name)
    assert not missing_fallbacks, (
        f"Primary tiers without a fallback: {missing_fallbacks}. "
        f"A primary-provider outage will brick every dispatch routed "
        f"to these tiers. Add a fallback in substrate/dispatch/config.yaml."
    )


def test_fallback_is_a_different_model_family(production_config):
    """CROSS-FAMILY MODEL INVARIANT — the load-bearing resilience test.

    Every tier's fallback must be a DIFFERENT MODEL FAMILY from its
    primary, never the same model served through a second provider door.
    A glm-5.2 -> glm-5.2 chain (even via different providers) is a single
    point of failure: a z.ai/GLM rate-limit, model deprecation, or
    provider-side outage takes down BOTH layers at once, so the
    "fallback" provides zero real resilience.

    Hardened 2026-07-06: the earlier ``test_fallbacks_route_to_the_other_family``
    checked only PROVIDER-NAME diversity (zai <-> openrouter), which passed
    against a glm-5.2 -> glm-5.2 monoculture because provider diversity
    happened to coincide with model diversity under the old Hermes/Grok <->
    OpenRouter/DeepSeek chain. Provider diversity is necessary but NOT
    sufficient: model outages are model-scoped, so the MODEL ITSELF must
    differ.
    """
    for tier_name in ALL_TIERS_WITH_FALLBACK:
        tier = production_config.tiers[tier_name]
        if tier.fallback is None:
            continue
        # Provider diversity: a single provider billing/key/ban event
        # must not take down both layers.
        assert tier.provider != tier.fallback.provider, (
            f"tier {tier_name!r} primary and fallback share provider "
            f"{tier.provider!r}; a single provider outage takes down "
            f"both layers — not cross-provider resilience."
        )
        # Model-family diversity (the real invariant): compare the base
        # model id after the last '/', so 'zai/glm-5.2' vs
        # 'openrouter/z-ai/glm-5.2' are correctly detected as the SAME
        # model (the monoculture this test was written to forbid).
        primary_model = tier.model.rsplit("/", 1)[-1]
        fallback_model = tier.fallback.model.rsplit("/", 1)[-1]
        assert primary_model != fallback_model, (
            f"tier {tier_name!r} falls back to the SAME model "
            f"({tier.model!r} -> {tier.fallback.model!r}); a single "
            f"model outage takes down both layers — not cross-family "
            f"resilience (see the posture comment in config.yaml)."
        )


def test_role_tier_mapping_routes_every_primary_role_to_a_defined_tier(
    production_config,
):
    """Roles in ``role_tiers`` must route to a tier that exists.
    Catches a typo'd tier name silently routing to a default."""
    for role, tier_name in production_config.role_tiers.items():
        assert tier_name in production_config.tiers, (
            f"role {role!r} routes to tier {tier_name!r} which is not defined"
        )


# ─────────────────────────────────────────────────────────────────────
# 2. Chaos: bridge down, every primary role still completes
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ROLES_ROUTED_TO_ZAI_PRIMARY)
def test_dispatch_falls_through_to_openrouter_when_zai_dies(
    role, production_config, _events_dir,
):
    """For every role that routes to a Hermes-primary tier (flash, pro,
    verify), when the Hermes provider raises, the dispatch must complete
    via the OpenRouter fallback. The successful event must have
    ``fallback_chain_index >= 1``. Synthesis is exempted during the
    Sprint 17-20 measurement window — see the companion test below."""
    failing = _FailingZaiProvider()
    working = _WorkingOpenRouterProvider()
    register_provider(failing)
    register_provider(working)

    investigation_id = f"inv-chaos-{role}"
    result = dispatch(
        "prompt", role, investigation_id=investigation_id,
        config=production_config,
    )

    assert result.provider == "openrouter", (
        f"role {role!r} did not fall through to openrouter; got provider="
        f"{result.provider!r}. Fallback chain broken."
    )
    assert result.fallback_chain_index >= 1
    # Sanity: the failing provider was actually invoked first
    assert len(failing.calls) == 1
    assert len(working.calls) == 1


@pytest.mark.parametrize("role", ROLES_ROUTED_TO_OPENROUTER_PRIMARY)
def test_synthesis_falls_through_to_zai_when_openrouter_dies(
    role, production_config, _events_dir,
):
    """Sprint 17-20 measurement-window companion to the Hermes-primary
    chaos test. The synthesis tier is OpenRouter-primary during the
    measurement window (master-spec §14.4); when OpenRouter dies the
    dispatch must fall through to Hermes. Without this, an OpenRouter
    outage during the measurement window would brick every synthesis
    dispatch and there would be no synthesis trajectory for the
    Sprint 20 verdict measurement."""
    failing = _FailingOpenRouterProvider()
    working = _WorkingZaiProvider()
    register_provider(failing)
    register_provider(working)

    investigation_id = f"inv-chaos-{role}-or-down"
    result = dispatch(
        "prompt", role, investigation_id=investigation_id,
        config=production_config,
    )

    assert result.provider == "zai", (
        f"role {role!r} did not fall through to zai; got provider="
        f"{result.provider!r}. OpenRouter-primary fallback chain broken."
    )
    assert result.fallback_chain_index >= 1
    assert len(failing.calls) == 1
    assert len(working.calls) == 1


def test_chaos_event_log_has_two_events_per_dispatch(production_config, _events_dir):
    """Failure + fallback both emit ``dispatch.call`` events. Without
    both events landing, post-hoc analytics can't tell the operator
    that the primary provider was the cause. Uses a zai-primary
    role (decomposer/pro) since synthesizer is OpenRouter-primary
    (opus, Sprint 17-20 measurement window)."""
    register_provider(_FailingZaiProvider())
    register_provider(_WorkingOpenRouterProvider())

    dispatch(
        "prompt", "decomposer", investigation_id="inv-chaos-events",
        config=production_config,
    )
    rows = trajectory("inv-chaos-events")
    assert len(rows) == 2, (
        f"expected primary-failure + fallback-success events, got {len(rows)}"
    )
    primary = Event.model_validate(rows[0])
    fb = Event.model_validate(rows[1])
    assert primary.payload.provider == "zai"
    assert primary.payload.finish_reason == "error"
    assert primary.payload.fallback_chain_index == 0
    assert fb.payload.provider == "openrouter"
    assert fb.payload.fallback_chain_index == 1
    assert fb.payload.finish_reason == "stop"
    assert fb.payload.input_tokens == 100
    assert fb.payload.output_tokens == 30


def test_chaos_dispatch_raises_when_both_layers_fail(
    production_config, _events_dir,
):
    """If the chaos extends to OpenRouter too (extreme worst case),
    the dispatch must raise. This is the worst-case posture the
    operator needs to know about: total substrate darkness when both
    providers are out."""

    class _FailingOpenRouter:
        name = "openrouter"

        def call(self, *, model, prompt, max_tokens, temperature):
            raise ProviderError(
                "simulated openrouter outage", provider=self.name,
                model=model, latency_ms=8,
            )

        def normalize_usage(self, raw_usage):
            return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)

    register_provider(_FailingZaiProvider())
    register_provider(_FailingOpenRouter())
    with pytest.raises(ProviderError):
        dispatch(
            "prompt", "synthesizer", investigation_id="inv-doubly-doomed",
            config=production_config,
        )
    rows = trajectory("inv-doubly-doomed")
    assert len(rows) == 2
    for row in rows:
        assert row["payload"]["finish_reason"] == "error"


# ─────────────────────────────────────────────────────────────────────
# 3. Verifier-tier defect regression
# ─────────────────────────────────────────────────────────────────────


def test_verifier_role_falls_through_to_openrouter(production_config, _events_dir):
    """Regression: the verify tier shipped without a fallback in an
    earlier draft of config.yaml. The verifier role is the one most
    directly responsible for catching substrate quality regressions —
    losing it during a bridge outage would silently degrade output
    quality without any external signal. Lock the fix in."""
    register_provider(_FailingZaiProvider())
    register_provider(_WorkingOpenRouterProvider())

    result = dispatch(
        "prompt", "verifier", investigation_id="inv-verifier-chaos",
        config=production_config,
    )
    assert result.provider == "openrouter"
    assert result.fallback_chain_index >= 1
