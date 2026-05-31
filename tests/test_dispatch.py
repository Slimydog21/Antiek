"""Tests for substrate/dispatch/.

What this file proves:

1. ``dispatch`` routes by role → tier → provider correctly.
2. The DispatchCall event lands with all required fields populated.
3. **Anthropic-shaped usage** (cache-EXCLUSIVE ``input_tokens`` +
   ``cache_read_input_tokens`` + ``cache_creation_input_tokens``) normalizes
   to an INCLUSIVE ``input_tokens`` (SPR-01).
4. **OpenAI-shaped usage** (``prompt_tokens`` / ``completion_tokens`` /
   ``prompt_tokens_details.cached_tokens``) normalizes correctly.
5. The fallback chain triggers when the primary raises ProviderError —
   two DispatchCall events emitted, second has ``fallback_chain_index=1``.
6. ``policy_id`` is stamped as ``{provider}/{model}`` on the event so
   the open-weight-trajectory filter in Loop 3 has the signal it needs.
7. ``context_pack_event_id`` round-trips onto the DispatchCall when
   provided.
8. Cost is computed in ONE place using ``NormalizedUsage`` and the tier
   pricing — adapters do not compute cost.
9. ``finish_reason`` normalization maps provider-native values into the
   Literal set on DispatchCallPayload.

These tests use **mocked providers** — no live API keys, no network.
Real adapters (Anthropic, OpenAI-compat over httpx) ship in a separate
turn and have their own smoke tests against real endpoints.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    dispatch,
    normalize_finish_reason,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import DispatchCallPayload, Event  # noqa: E402

# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class _MockAnthropicProvider:
    """Returns Anthropic-shaped usage. Used to verify normalization works
    on the production Anthropic API shape without hitting the network."""

    name = "mock-anthropic"

    def __init__(self, *, raise_on_call: bool = False, finish: str = "end_turn"):
        self._raise = raise_on_call
        self._finish = finish
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model, "max_tokens": max_tokens})
        if self._raise:
            raise ProviderError(
                "mocked failure", provider=self.name, model=model, latency_ms=123,
            )
        return RawProviderResponse(
            text="anthropic response text",
            # Anthropic's ``input_tokens`` is the cache-EXCLUSIVE remainder
            # (tokens after the last cache breakpoint); cache_read /
            # cache_creation are reported SEPARATELY and are NOT inside it.
            # Inclusive input total here = 1200 + 800 + 0 = 2000.
            raw_usage={
                "input_tokens": 1200,            # post-breakpoint remainder
                "output_tokens": 350,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 800,  # read from cache, NOT in input_tokens
            },
            finish_reason=self._finish,
            latency_ms=890,
            request_id="req_abc",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        # Mirror the production AnthropicProvider contract (SPR-01): the raw
        # ``input_tokens`` is cache-exclusive, so sum in cache_read and
        # cache_creation to present the router an INCLUSIVE total, and forward
        # both subsets so cost is billed at their own rates.
        remainder = int(raw_usage.get("input_tokens", 0))
        cache_read = int(raw_usage.get("cache_read_input_tokens", 0))
        cache_creation = int(raw_usage.get("cache_creation_input_tokens", 0))
        return NormalizedUsage(
            input_tokens=remainder + cache_read + cache_creation,
            output_tokens=int(raw_usage.get("output_tokens", 0)),
            cached_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )


class _MockOpenAICompatProvider:
    """Returns OpenAI-shape usage. Verifies the alternative normalization
    path without hitting the network. DeepSeek and MiMo both speak this
    shape today."""

    name = "mock-openai-compat"

    def __init__(self, *, raise_on_call: bool = False, finish: str = "stop"):
        self._raise = raise_on_call
        self._finish = finish
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model, "max_tokens": max_tokens})
        if self._raise:
            raise ProviderError(
                "mocked failure", provider=self.name, model=model, latency_ms=77,
            )
        return RawProviderResponse(
            text="openai-compat response text",
            raw_usage={
                "prompt_tokens": 2000,
                "completion_tokens": 500,
                "total_tokens": 2500,
                "prompt_tokens_details": {"cached_tokens": 1500},
            },
            finish_reason=self._finish,
            latency_ms=420,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        details = raw_usage.get("prompt_tokens_details") or {}
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
            cached_input_tokens=int(details.get("cached_tokens", 0)),
        )


# ---------------------------------------------------------------------------
# Test config — small, in-memory, no YAML parsing in tests.
# ---------------------------------------------------------------------------


def _two_tier_config() -> DispatchConfig:
    """One Anthropic-shaped tier with one OpenAI-compat fallback."""
    flash_pricing = TierPricing(
        input_per_mtok=0.14, output_per_mtok=0.28, cached_input_per_mtok=0.014,
    )
    synthesis_pricing = TierPricing(
        input_per_mtok=15.0, output_per_mtok=75.0, cached_input_per_mtok=1.5,
    )
    fallback = TierConfig(
        name="flash__fallback", provider="mock-openai-compat", model="mimo-flash",
        max_tokens=4096, temperature=0.2, context_budget_tokens=32000,
        pricing=flash_pricing, fallback=None,
    )
    flash = TierConfig(
        name="flash", provider="mock-openai-compat", model="deepseek-flash",
        max_tokens=4096, temperature=0.2, context_budget_tokens=32000,
        pricing=flash_pricing, fallback=None,
    )
    synthesis = TierConfig(
        name="synthesis", provider="mock-anthropic", model="claude-opus-4-7",
        max_tokens=8192, temperature=0.4, context_budget_tokens=256000,
        pricing=synthesis_pricing, fallback=fallback,
    )
    return DispatchConfig(
        role_tiers={"decomposer": "flash", "synthesizer": "synthesis"},
        tiers={"flash": flash, "synthesis": synthesis},
    )


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def _events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(d))
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dispatch_routes_by_role_to_correct_tier(_events_dir):
    anthropic = _MockAnthropicProvider()
    openai_compat = _MockOpenAICompatProvider()
    register_provider(anthropic)
    register_provider(openai_compat)

    result = dispatch(
        "what is X?", "synthesizer",
        investigation_id="inv-1", config=_two_tier_config(),
    )

    assert result.tier == "synthesis"
    assert result.provider == "mock-anthropic"
    assert result.model == "claude-opus-4-7"
    assert result.fallback_chain_index == 0
    assert anthropic.calls == [{"model": "claude-opus-4-7", "max_tokens": 8192}]
    assert openai_compat.calls == []


def test_dispatch_emits_dispatch_call_event(_events_dir):
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    dispatch(
        "hello", "synthesizer", investigation_id="inv-evt",
        config=_two_tier_config(),
        context_pack_event_id="evt-pack-1",
    )

    rows = trajectory("inv-evt")
    assert len(rows) == 1
    event = Event.model_validate(rows[0])
    assert isinstance(event.payload, DispatchCallPayload)
    p = event.payload
    assert p.provider == "mock-anthropic"
    assert p.model == "claude-opus-4-7"
    assert p.tier == "synthesis"
    assert p.target_role == "synthesizer"
    assert p.fallback_chain_index == 0
    assert p.context_pack_event_id == "evt-pack-1"
    assert p.finish_reason == "stop"  # 'end_turn' → 'stop'
    assert event.policy_id == "mock-anthropic/claude-opus-4-7"


def test_anthropic_usage_normalization(_events_dir):
    """Watch-item: Anthropic's raw ``input_tokens`` is the cache-EXCLUSIVE
    remainder; cache_read / cache_creation are reported separately. The
    adapter sums them into an INCLUSIVE ``input_tokens`` (SPR-01) and forwards
    the cached-read subset for the router's cached-input discount."""
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "hi", "synthesizer", investigation_id="inv-an",
        config=_two_tier_config(),
    )
    # Inclusive total = remainder(1200) + cache_read(800) + cache_creation(0).
    assert result.usage.input_tokens == 2000
    assert result.usage.output_tokens == 350
    assert result.usage.cached_input_tokens == 800


def test_openai_compat_usage_normalization(_events_dir):
    """Watch-item: OpenAI-compatible returns prompt_tokens /
    completion_tokens, with prompt_tokens_details.cached_tokens for the
    cached subset."""
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "hi", "decomposer", investigation_id="inv-oa",
        config=_two_tier_config(),
    )
    assert result.usage.input_tokens == 2000
    assert result.usage.output_tokens == 500
    assert result.usage.cached_input_tokens == 1500


def test_cost_uses_cached_pricing_discount(_events_dir):
    """The cost computation must apply the cached-input rate to the
    cached portion. If we ever fold cached tokens into the full input
    rate by accident, every cost report becomes overstated."""
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    result = dispatch(
        "hi", "synthesizer", investigation_id="inv-cost",
        config=_two_tier_config(),
    )
    # Inclusive input = 2000 (1200 remainder + 800 cache_read), 800 cached,
    # 0 cache_creation, so paid-full = max(0, 2000-800-0) = 1200.
    # Synthesis pricing: $15/Mtok input, $1.5/Mtok cached input, $75/Mtok output.
    # cost = (1200/1e6)*15 + (800/1e6)*1.5 + (350/1e6)*75
    #      = 0.018 + 0.0012 + 0.02625 = 0.04545
    assert result.cost_usd == pytest.approx(0.04545, rel=1e-6)


def test_fallback_chain_triggers_on_primary_failure(_events_dir):
    """When the primary raises, the fallback fires and TWO DispatchCall
    events land — the failed primary (finish_reason='error',
    fallback_chain_index=0) and the successful fallback (chain_index=1)."""
    failing = _MockAnthropicProvider(raise_on_call=True)
    register_provider(failing)
    register_provider(_MockOpenAICompatProvider())

    result = dispatch(
        "hi", "synthesizer", investigation_id="inv-fb",
        config=_two_tier_config(),
    )

    assert result.fallback_chain_index == 1
    assert result.provider == "mock-openai-compat"
    assert result.model == "mimo-flash"

    rows = trajectory("inv-fb")
    assert len(rows) == 2
    primary = Event.model_validate(rows[0])
    fb = Event.model_validate(rows[1])
    assert primary.payload.fallback_chain_index == 0
    assert primary.payload.finish_reason == "error"
    assert primary.payload.provider == "mock-anthropic"
    assert primary.payload.input_tokens == 0  # no usage on failure
    assert primary.payload.cost_usd == 0.0
    assert fb.payload.fallback_chain_index == 1
    assert fb.payload.provider == "mock-openai-compat"


def test_dispatch_raises_when_all_tiers_fail(_events_dir):
    """If every tier in the chain fails, dispatch raises the last
    ProviderError. The events for the failed attempts still land."""
    register_provider(_MockAnthropicProvider(raise_on_call=True))
    register_provider(_MockOpenAICompatProvider(raise_on_call=True))
    with pytest.raises(ProviderError):
        dispatch(
            "hi", "synthesizer", investigation_id="inv-doomed",
            config=_two_tier_config(),
        )
    rows = trajectory("inv-doomed")
    # Two failure events: primary + one fallback.
    assert len(rows) == 2
    for row in rows:
        assert row["payload"]["finish_reason"] == "error"


def test_unknown_role_raises(_events_dir):
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    with pytest.raises(KeyError, match="role_tiers"):
        dispatch(
            "hi", "no-such-role", investigation_id="inv-x",
            config=_two_tier_config(),
        )


def test_finish_reason_normalization():
    """Direct test of the helper — adapters MAY use it, but the router
    also applies it before emit. Either path produces the closed Literal
    set on DispatchCallPayload."""
    assert normalize_finish_reason(None) is None
    assert normalize_finish_reason("end_turn") == "stop"
    assert normalize_finish_reason("stop_sequence") == "stop"
    assert normalize_finish_reason("max_tokens") == "length"
    assert normalize_finish_reason("stop") == "stop"
    assert normalize_finish_reason("length") == "length"
    assert normalize_finish_reason("content_filter") == "content_filter"
    assert normalize_finish_reason("tool_use") == "tool_use"
    assert normalize_finish_reason("tool_calls") == "tool_use"
    # Unknown provider value maps to 'error' — queryable rather than silent.
    assert normalize_finish_reason("something_new") == "error"


def test_max_tokens_override(_events_dir):
    """Caller can override the tier default. The override flows to the
    provider call; the tier default is used otherwise."""
    p = _MockAnthropicProvider()
    register_provider(p)
    register_provider(_MockOpenAICompatProvider())
    dispatch(
        "hi", "synthesizer", investigation_id="inv-ov",
        config=_two_tier_config(),
        max_tokens=512,
    )
    assert p.calls[0]["max_tokens"] == 512


def test_config_loads_from_yaml_file():
    """Sanity: the scaffolded config.yaml parses into a DispatchConfig.
    The scaffold uses providers that aren't registered yet, so we don't
    actually dispatch — we just verify the parse."""
    config_path = Path(__file__).parent.parent / "substrate" / "dispatch" / "config.yaml"
    config = DispatchConfig.from_yaml(config_path)
    assert "flash" in config.tiers
    assert "synthesis" in config.tiers
    assert config.role_tiers["synthesizer"] == "synthesis"
    # Sprint 17 dispatch tier-differentiation measurement (2026-05-19,
    # master-spec §14.4 + sprint17 spec §1.2): synthesis tier inverted
    # to Opus 4.7 primary via OpenRouter, Hermes/Grok fallback, for a
    # 2-week measurement window. Verdict at Sprint 20 either flips
    # back to Hermes primary (cost grounds) or keeps Opus primary
    # (operator-acceptable-synthesis denominator). The flash, pro,
    # and verify tiers stay Hermes primary — only synthesis is under
    # measurement.
    syn = config.tiers["synthesis"]
    assert syn.provider == "openrouter"
    assert syn.model == "anthropic/claude-opus-4.7"
    assert syn.fallback is not None
    assert syn.fallback.provider == "hermes"
    assert syn.fallback.model == "grok-4.3"


def test_config_role_tiers_covers_every_dispatching_role():
    """Regression for 2026-05-18 production incident.

    ``skills/domain/extract.py`` dispatches with
    ``role="knowledge_extractor"``. Without that key in
    ``role_tiers``, the router raises
    ``KeyError("Role 'knowledge_extractor' not in config.role_tiers")``
    and Phase 8 ends with an empty ``auto_patch_applied`` event,
    which then fails the Phase 8 postcondition and bricks the whole
    investigation. Lock in every role that the code dispatches with
    so a future refactor that adds a role doesn't silently regress."""
    config_path = Path(__file__).parent.parent / "substrate" / "dispatch" / "config.yaml"
    config = DispatchConfig.from_yaml(config_path)
    required_roles = {
        "decomposer", "evidence_retriever", "parameter_extractor",
        "connector", "synthesizer", "user_agent", "note_taker",
        "challenger", "grounder", "tier_assigner", "constraint_checker",
        "verifier", "knowledge_extractor",
    }
    missing = required_roles - set(config.role_tiers)
    assert not missing, (
        f"role_tiers missing entries for {missing}. Any role the code "
        f"dispatches must be present here or the router raises KeyError."
    )
