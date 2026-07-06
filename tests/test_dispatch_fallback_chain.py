"""Chaos test for the claude-less dispatch chain: GLM-5.2 → DeepSeek → MiMo.

Loads the **production** ``substrate/dispatch/config.yaml`` (not a synthetic
test config) and proves that every tier completes when its primary dies,
walking a THREE-LAYER direct-API fallback chain:

    GLM-5.2 (zai / zai_reasoning) → DeepSeek V4 Pro → Xiaomi MiMo V2.5 Pro

This is the architectural insurance test for the operator's claude-less
model-footprint decision (2026-07-06): GLM-5.2 is the primary AI driver for
every tier including synthesis; DeepSeek and MiMo are the cross-family
backups via their DIRECT APIs (no OpenRouter hop, no Anthropic). Without
this file, ``config.yaml`` could quietly lose a fallback layer or regress
to a monoculture (e.g. a glm-5.2 → glm-5.2 chain) and no test would catch
it until a real provider outage took the substrate dark.

Why these stubs and not the real providers: the chaos test injects
``_FailingXxxProvider`` / ``_WorkingXxxProvider`` doubles into the
registry so the walk is deterministic and offline — the real provider
network shapes are unit-tested in ``test_provider_openai_compat.py``.
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

# Architectural posture (operator decision 2026-07-06): claude-less.
# flash/pro/verify primary on `zai` (GLM-5.2, thinking disabled).
# synthesis primary on `zai_reasoning` (GLM-5.2, thinking enabled).
# Every tier falls GLM → DeepSeek → MiMo (direct APIs).
ALL_TIERS_WITH_FALLBACK = ("flash", "pro", "synthesis", "verify")
# Both GLM providers share the z.ai endpoint + Z_AI_API_KEY; the router
# sees them as two distinct registered providers (thinking policy differs).
GLM_PROVIDER_NAMES = ("zai", "zai_reasoning")
# Roles routed to the thinking-disabled GLM tiers (flash/pro/verify).
ROLES_ROUTED_TO_ZAI_PRIMARY = (
    "decomposer",          # pro
    "evidence_retriever",  # flash
    "verifier",            # verify
    "note_taker",          # flash
    "user_agent",          # pro
)
# Synthesis is the only thinking-enabled tier (zai_reasoning primary).
ROLES_ROUTED_TO_ZAI_REASONING_PRIMARY = (
    "synthesizer",         # synthesis
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

    Loaded once per test module since the YAML is static for the session."""
    cfg_path = Path(__file__).resolve().parents[1] / "substrate" / "dispatch" / "config.yaml"
    return DispatchConfig.from_yaml(cfg_path)


# ─────────────────────────────────────────────────────────────────────
# Stub providers (one failing + one working per family in the chain)
# ─────────────────────────────────────────────────────────────────────


class _FailingZaiProvider:
    """Simulates GLM-5.2 (zai) being down. Every call raises ProviderError,
    which is what the router needs to see to walk to ``tier.fallback``."""

    name = "zai"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        raise ProviderError(
            "simulated zai outage", provider=self.name, model=model, latency_ms=12,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)


class _FailingZaiReasoningProvider(_FailingZaiProvider):
    """Same as _FailingZaiProvider but registered under the synthesis
    tier's thinking-enabled GLM name."""

    name = "zai_reasoning"


class _WorkingDeepSeekProvider:
    """First-link fallback. Returns a realistic OpenAI-shape response so
    the router's usage normalization + dispatch.call event emission
    paths exercise correctly under the fallback case."""

    name = "deepseek"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        return RawProviderResponse(
            text="fallback — glm was down, deepseek handled it",
            raw_usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            finish_reason="stop", latency_ms=420,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
            cached_input_tokens=0,
        )


class _FailingDeepSeekProvider:
    """Mirror for the two-layer-down chaos case: when both GLM and
    DeepSeek are out, the router must walk on to MiMo."""

    name = "deepseek"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        raise ProviderError(
            "simulated deepseek outage", provider=self.name, model=model, latency_ms=10,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)


class _WorkingXiaomiProvider:
    """Last-link fallback. The tier survives only if this registers."""

    name = "xiaomi"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model})
        return RawProviderResponse(
            text="fallback — glm + deepseek down, mimo handled it",
            raw_usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            finish_reason="stop", latency_ms=510,
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
    """Every primary tier must carry at least one fallback link — a tier
    with no fallback is a substrate-dark hazard the moment its primary
    fails."""
    for tier_name in ALL_TIERS_WITH_FALLBACK:
        tier = production_config.tiers.get(tier_name)
        assert tier is not None, f"tier {tier_name!r} not defined in config"
        assert tier.fallback is not None, (
            f"tier {tier_name!r} has NO fallback — a single provider outage "
            f"bricks every call on this tier."
        )


def test_fallback_is_a_different_model_family(production_config):
    """CROSS-FAMILY MODEL INVARIANT — the load-bearing resilience test.

    Every ADJACENT link in each tier's fallback chain must be a DIFFERENT
    MODEL FAMILY (and a different provider) from its neighbour — never the
    same model behind a second provider door. Walks the WHOLE chain, not
    just one link, because the chain is now three-deep (GLM → DeepSeek →
    MiMo) and a monoculture could hide at depth 2.

    A glm-5.2 → glm-5.2 link (even via distinct provider names) is a single
    point of failure: a z.ai/GLM rate-limit, deprecation, or outage takes
    both layers at once. Provider-name diversity is necessary but NOT
    sufficient; the MODEL ITSELF must differ at every hop. Compare the base
    model id after the last '/', so 'zai/glm-5.2' vs 'openrouter/z-ai/glm-5.2'
    are correctly detected as the SAME model.
    """
    for tier_name in ALL_TIERS_WITH_FALLBACK:
        current = production_config.tiers[tier_name]
        assert current.fallback is not None
        depth = 0
        while current.fallback is not None:
            nxt = current.fallback
            assert current.provider != nxt.provider, (
                f"tier {tier_name!r} link {depth}: adjacent providers share "
                f"{current.provider!r}; one provider outage takes both layers."
            )
            cur_model = (current.model or "").rsplit("/", 1)[-1]
            nxt_model = (nxt.model or "").rsplit("/", 1)[-1]
            assert cur_model != nxt_model, (
                f"tier {tier_name!r} link {depth} falls to the SAME model "
                f"({current.model!r} -> {nxt.model!r}); a model-scoped outage "
                f"takes both layers — not cross-family resilience."
            )
            current = nxt
            depth += 1
            assert depth < 8, f"tier {tier_name!r} fallback chain is cyclic"


def test_fallback_chain_is_at_least_two_layers_deep(production_config):
    """The operator's directive (2026-07-06) is GLM + TWO backups. That
    means a THREE-node chain (primary + 2 fallbacks). This test mechanically
    enforces the depth the recursive parser change (router.py
    ``_fallback_tier_config``) unlocks — catching a regression to a
    one-deep chain silently re-introduced by a config edit."""
    for tier_name in ALL_TIERS_WITH_FALLBACK:
        current = production_config.tiers[tier_name]
        assert current.fallback is not None
        depth = 1
        node = current.fallback
        while node.fallback is not None:
            node = node.fallback
            depth += 1
        assert depth >= 2, (
            f"tier {tier_name!r} chain is only {depth} link(s) deep; the "
            f"operator directive requires GLM + two backups (>= 2 links)."
        )


def test_routing_is_claudeless_and_direct_api(production_config):
    """OPERATOR DIRECTIVE ENFORCEMENT (2026-07-06): the model footprint is
    claude-less and uses DIRECT provider APIs only (no OpenRouter hop, no
    Anthropic). Mechanically enforced so a future config edit cannot quietly
    re-introduce Claude or OpenRouter without turning this test red."""
    forbidden_providers = {"openrouter", "anthropic"}
    forbidden_model_fragments = ("claude", "anthropic/")
    for tier_name, tier in production_config.tiers.items():
        node = tier
        while node is not None:
            assert node.provider not in forbidden_providers, (
                f"tier {tier_name!r} routes through {node.provider!r}; the "
                f"footprint must be claude-less + direct-API only."
            )
            model = (node.model or "").lower()
            for frag in forbidden_model_fragments:
                assert frag not in model, (
                    f"tier {tier_name!r} uses model {node.model!r} containing "
                    f"{frag!r}; the footprint must be claude-less."
                )
            node = node.fallback


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
# 2. Chaos: GLM down, every primary role still completes
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ROLES_ROUTED_TO_ZAI_PRIMARY)
def test_dispatch_falls_through_to_deepseek_when_zai_dies(
    role, production_config, _events_dir,
):
    """For every role on a thinking-disabled GLM tier (flash/pro/verify),
    when the zai provider raises, the dispatch must complete via the
    DeepSeek first-link fallback."""
    failing = _FailingZaiProvider()
    working = _WorkingDeepSeekProvider()
    register_provider(failing)
    register_provider(working)

    investigation_id = f"inv-chaos-{role}"
    result = dispatch(
        "prompt", role, investigation_id=investigation_id, config=production_config,
    )

    assert result.provider == "deepseek", (
        f"role {role!r} did not fall through to deepseek; got "
        f"provider={result.provider!r}. Fallback chain broken."
    )
    assert result.fallback_chain_index >= 1
    assert len(failing.calls) == 1
    assert len(working.calls) == 1


@pytest.mark.parametrize("role", ROLES_ROUTED_TO_ZAI_REASONING_PRIMARY)
def test_synthesis_falls_through_to_deepseek_when_zai_reasoning_dies(
    role, production_config, _events_dir,
):
    """The synthesis tier is thinking-enabled-GLM primary (zai_reasoning).
    When that provider dies the dispatch must fall through to DeepSeek —
    the same first link the other tiers use, proving synthesis is not
    orphaned by its distinct provider name."""
    failing = _FailingZaiReasoningProvider()
    working = _WorkingDeepSeekProvider()
    register_provider(failing)
    register_provider(working)

    investigation_id = f"inv-chaos-{role}-zai-down"
    result = dispatch(
        "prompt", role, investigation_id=investigation_id, config=production_config,
    )

    assert result.provider == "deepseek", (
        f"role {role!r} did not fall through to deepseek; got "
        f"provider={result.provider!r}. Synthesis chain broken."
    )
    assert result.fallback_chain_index >= 1
    assert len(failing.calls) == 1
    assert len(working.calls) == 1


@pytest.mark.parametrize("role", ROLES_ROUTED_TO_ZAI_PRIMARY)
def test_dispatch_walks_two_links_to_mimo_when_glm_and_deepseek_die(
    role, production_config, _events_dir,
):
    """THREE-LAYER CHAOS: when both GLM (zai) and DeepSeek are down, the
    dispatch must walk TWO links to the MiMo third node. This is the test
    that proves the recursive fallback chain actually works at runtime —
    not just that it parses. Without it the second backup is dead weight."""
    register_provider(_FailingZaiProvider())
    register_provider(_FailingDeepSeekProvider())
    working = _WorkingXiaomiProvider()
    register_provider(working)

    investigation_id = f"inv-chaos3-{role}"
    result = dispatch(
        "prompt", role, investigation_id=investigation_id, config=production_config,
    )

    assert result.provider == "xiaomi", (
        f"role {role!r} did not walk two links to mimo; got "
        f"provider={result.provider!r}. Third-layer fallback broken."
    )
    assert result.fallback_chain_index >= 2, (
        f"role {role!r} reached provider={result.provider!r} at chain index "
        f"{result.fallback_chain_index}; expected >= 2 (the mimo link)."
    )


def test_chaos_event_log_has_two_events_per_dispatch(production_config, _events_dir):
    """Failure + fallback both emit ``dispatch.call`` events. Without both
    landing, post-hoc analytics can't tell the operator the primary was the
    cause. Uses a zai-primary role (decomposer/pro)."""
    register_provider(_FailingZaiProvider())
    register_provider(_WorkingDeepSeekProvider())

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
    assert fb.payload.provider == "deepseek"
    assert fb.payload.fallback_chain_index == 1
    assert fb.payload.finish_reason == "stop"
    assert fb.payload.input_tokens == 100
    assert fb.payload.output_tokens == 30


def test_chaos_dispatch_raises_when_all_three_layers_fail(production_config, _events_dir):
    """Worst case: all three providers (GLM, DeepSeek, MiMo) are out. The
    dispatch must raise — total substrate darkness is surfaced, not
    swallowed. Proves the chain terminates correctly rather than looping."""

    class _FailingXiaomi:
        name = "xiaomi"

        def call(self, *, model, prompt, max_tokens, temperature):
            raise ProviderError(
                "simulated mimo outage", provider=self.name, model=model, latency_ms=8,
            )

        def normalize_usage(self, raw_usage):
            return NormalizedUsage(input_tokens=0, output_tokens=0, cached_input_tokens=0)

    register_provider(_FailingZaiProvider())
    register_provider(_FailingDeepSeekProvider())
    register_provider(_FailingXiaomi())
    with pytest.raises(ProviderError):
        dispatch(
            "prompt", "synthesizer", investigation_id="inv-doubly-doomed",
            config=production_config,
        )
    rows = trajectory("inv-doubly-doomed")
    # Three failure events — one per layer walked.
    assert len(rows) == 3
    for row in rows:
        assert row["payload"]["finish_reason"] == "error"


# ─────────────────────────────────────────────────────────────────────
# 3. Verifier-tier defect regression
# ─────────────────────────────────────────────────────────────────────


def test_verifier_role_falls_through_to_deepseek(production_config, _events_dir):
    """Regression: the verify tier once shipped without a fallback. The
    verifier role catches substrate quality regressions — losing it during
    a GLM outage would silently degrade output quality. Lock the fallback
    in (now two layers deep: → DeepSeek → MiMo)."""
    register_provider(_FailingZaiProvider())
    register_provider(_WorkingDeepSeekProvider())

    result = dispatch(
        "prompt", "verifier", investigation_id="inv-verifier-chaos",
        config=production_config,
    )
    assert result.provider == "deepseek"
    assert result.fallback_chain_index >= 1
