"""The dispatch router.

Single entry point: ``dispatch(prompt, role, ...)``. Routes by ``role``
to a tier from ``config.yaml``; calls the provider; emits a
``DispatchCall`` event; falls back if the primary fails.

Discipline:

- The router NEVER inspects provider-native usage shapes. Each adapter
  normalizes its own usage. See ``base.py``.
- Cost is computed in ONE place (this module) from
  ``NormalizedUsage + TierConfig.pricing``. Adapters do not compute cost.
- The router does NOT import from ``substrate.context_pack``. The two
  modules meet only at the call site — the caller passes
  ``context_pack_event_id`` in, the router records it on the
  ``DispatchCall`` event but never opens the pack.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import]

# Package-relative imports with a fall-back for direct-script execution.
try:
    from ..event_log import emit_typed
    from ..schemas import DispatchCallPayload
    from .base import (
        NormalizedUsage,
        Provider,
        ProviderError,
    )
    from .engagement_mode import (
        EngagementPolicy,
        resolve_latency_mode,
        resolve_tier_name,
    )
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from dispatch.base import (  # type: ignore[no-redef]
        NormalizedUsage,
        Provider,
        ProviderError,
    )
    from dispatch.engagement_mode import (  # type: ignore[no-redef]
        EngagementPolicy,
        resolve_latency_mode,
        resolve_tier_name,
    )
    from event_log import emit_typed  # type: ignore[no-redef]
    from schemas import DispatchCallPayload  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Config types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TierPricing:
    """USD-per-million-tokens for one (provider, model). Cached input is
    typically 90% off for Anthropic, 50% off for OpenAI-compatible. Zero
    means unknown — cost_usd will be zero for calls under this tier."""

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0
    cached_input_per_mtok: float = 0.0


@dataclass(frozen=True)
class TierConfig:
    """One tier from ``config.yaml``. The optional ``fallback`` carries
    another TierConfig to try when the primary call raises ProviderError."""

    name: str
    provider: str | None
    model: str | None
    max_tokens: int
    temperature: float
    context_budget_tokens: int
    pricing: TierPricing = field(default_factory=TierPricing)
    fallback: TierConfig | None = None


@dataclass(frozen=True)
class DispatchConfig:
    """Loaded ``config.yaml``. Use ``DispatchConfig.from_yaml(path)`` or
    construct directly for tests."""

    role_tiers: Mapping[str, str]  # role name → tier name
    tiers: Mapping[str, TierConfig]
    engagement_policy: EngagementPolicy | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> DispatchConfig:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: Mapping[str, Any]) -> DispatchConfig:
        tier_defaults: Mapping[str, Any] = data.get("tier_defaults", {})
        tiers: dict[str, TierConfig] = {}

        # Two-pass: first pass builds tiers without fallbacks (so they can
        # reference each other by name); second pass resolves fallbacks.
        for tier_name, tier_data in data["tiers"].items():
            defaults = tier_defaults.get(tier_name, {})
            pricing_data = tier_data.get("pricing", {})
            tiers[tier_name] = TierConfig(
                name=tier_name,
                provider=tier_data.get("provider"),
                model=tier_data.get("model"),
                max_tokens=defaults.get("max_tokens", 4096),
                temperature=defaults.get("temperature", 0.2),
                context_budget_tokens=defaults.get("context_budget_tokens", 32000),
                pricing=TierPricing(
                    input_per_mtok=pricing_data.get("input_per_mtok", 0.0),
                    output_per_mtok=pricing_data.get("output_per_mtok", 0.0),
                    cached_input_per_mtok=pricing_data.get("cached_input_per_mtok", 0.0),
                ),
                fallback=None,
            )

        # Resolve fallbacks. The fallback in YAML is an inline
        # {provider, model} dict — we wrap it as a one-deep TierConfig.
        # Multi-level chains are achievable by referencing a named tier
        # via "fallback_tier" instead; not used today.
        resolved: dict[str, TierConfig] = {}
        for tier_name, tier_data in data["tiers"].items():
            base = tiers[tier_name]
            fallback_obj: TierConfig | None = None
            fb = tier_data.get("fallback")
            if isinstance(fb, dict):
                fallback_obj = TierConfig(
                    name=f"{tier_name}__fallback",
                    provider=fb.get("provider"),
                    model=fb.get("model"),
                    max_tokens=base.max_tokens,
                    temperature=base.temperature,
                    context_budget_tokens=base.context_budget_tokens,
                    pricing=base.pricing,  # same pricing — providers usually align within a tier
                    fallback=None,
                )
            resolved[tier_name] = TierConfig(
                name=tier_name,
                provider=base.provider,
                model=base.model,
                max_tokens=base.max_tokens,
                temperature=base.temperature,
                context_budget_tokens=base.context_budget_tokens,
                pricing=base.pricing,
                fallback=fallback_obj,
            )

        engagement = EngagementPolicy.from_dict(data.get("engagement_policy"))
        return cls(
            role_tiers=data.get("role_tiers", {}),
            tiers=resolved,
            engagement_policy=engagement,
        )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


_PROVIDER_REGISTRY: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    """Register a provider adapter. Idempotent — re-registering replaces."""
    _PROVIDER_REGISTRY[provider.name] = provider


def get_provider(name: str) -> Provider:
    if name not in _PROVIDER_REGISTRY:
        raise KeyError(
            f"Provider {name!r} is not registered. Known: "
            f"{sorted(_PROVIDER_REGISTRY)}"
        )
    return _PROVIDER_REGISTRY[name]


def reset_provider_registry() -> None:
    """For tests only. Production code never calls this."""
    _PROVIDER_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Dispatch result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchResult:
    """What the caller receives from ``dispatch(...)``. Always represents a
    SUCCESSFUL call — if all fallbacks failed, ``dispatch`` raises."""

    text: str
    usage: NormalizedUsage
    cost_usd: float
    latency_ms: int
    provider: str
    model: str
    tier: str
    finish_reason: str | None
    fallback_chain_index: int  # 0 = primary, 1 = first fallback, etc.
    event_id: str | None  # the DispatchCall event_id for this success


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_prefix(s: str, n: int = 12) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


# Anthropic prompt-caching pricing multiplier: a 5-minute cache WRITE
# (``cache_creation_input_tokens``) is billed at 1.25x the base input rate.
# (Cache READS are 0.1x base input and are configured directly as
# ``cached_input_per_mtok`` in config.yaml — e.g. synthesis input 5.0 ->
# cached 0.50.) The write multiplier is derived from the base input rate
# rather than stored as a separate config field so config.yaml pricing
# stays a single source of truth and no new tier knob is required.
# Source: Anthropic prompt-caching docs — 5-min cache write = 1.25x base
# input price; cache read = 0.1x base input price.
_CACHE_WRITE_MULTIPLIER = 1.25


def _compute_cost_usd(usage: NormalizedUsage, pricing: TierPricing) -> float:
    """One place computes cost. Adapters do not.

    ``usage.input_tokens`` is the INCLUSIVE total (see ``NormalizedUsage``):
    it already contains the cache-read and cache-write subsets. The paid,
    uncached, non-written remainder is therefore the inclusive total minus
    BOTH cached subsets. ``max(0, ...)`` guards only against a malformed
    payload where the subsets exceed the total; on a normal cache hit the
    inclusive total is >= cached so it no longer clamps to zero (the old
    underbilling bug, which double-subtracted because Anthropic's adapter
    reported a cache-exclusive ``input_tokens``)."""
    paid_input = max(
        0,
        usage.input_tokens
        - usage.cached_input_tokens
        - usage.cache_creation_input_tokens,
    )
    return (
        (paid_input / 1_000_000.0) * pricing.input_per_mtok
        + (usage.cached_input_tokens / 1_000_000.0) * pricing.cached_input_per_mtok
        + (usage.cache_creation_input_tokens / 1_000_000.0)
        * pricing.input_per_mtok
        * _CACHE_WRITE_MULTIPLIER
        + (usage.output_tokens / 1_000_000.0) * pricing.output_per_mtok
    )


# Map provider-native finish reasons into the closed Literal set on
# DispatchCallPayload. The adapter normalizes — this helper is just for
# adapters to share.
_FINISH_REASON_MAP = {
    # Anthropic
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_use",
    # OpenAI-compatible
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    # Error / unknown
    "error": "error",
}


def normalize_finish_reason(provider_native: str | None) -> str | None:
    """Map a provider's finish reason into the DispatchCallPayload Literal
    set. Returns None if input is None; returns 'error' for unknown values
    (so the failure mode is queryable rather than silent)."""
    if provider_native is None:
        return None
    return _FINISH_REASON_MAP.get(provider_native, "error")


# ---------------------------------------------------------------------------
# The dispatch function
# ---------------------------------------------------------------------------


def _emit_dispatch_call(
    *,
    investigation_id: str,
    parent_event_id: str | None,
    role: str,
    tier: str,
    provider: str,
    model: str,
    usage: NormalizedUsage,
    cost_usd: float,
    latency_ms: int,
    verification_required: bool,
    fallback_chain_index: int,
    prompt_hash: str,
    finish_reason: str | None,
    context_pack_event_id: str | None,
) -> str | None:
    """Emit one DispatchCall event. Returns the event_id."""
    return emit_typed(
        investigation_id,
        DispatchCallPayload(
            provider=provider,
            model=model,
            tier=tier,  # type: ignore[arg-type]
            target_role=role,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            verification_required=verification_required,
            fallback_chain_index=fallback_chain_index,
            prompt_hash=prompt_hash,
            finish_reason=finish_reason,  # type: ignore[arg-type]
            context_pack_event_id=context_pack_event_id,
        ),
        parent_event_id=parent_event_id,
        role=role,
        policy_id=f"{provider}/{model}",
    )


def dispatch(
    prompt: str,
    role: str,
    *,
    investigation_id: str,
    max_tokens: int | None = None,
    verification_required: bool = False,
    context_pack_event_id: str | None = None,
    parent_event_id: str | None = None,
    config: DispatchConfig | None = None,
    config_path: str | Path | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    latency_mode: str | None = None,
    brain: str | None = None,
    deliverable_speed_preference: bool = False,
) -> DispatchResult:
    """Route an LLM call.

    Args:
        prompt: The assembled prompt to send. The router does not modify
            it — context-pack assembly is the caller's responsibility.
        role: One of ``substrate.constants.ROLES``. The router looks up
            the role's tier in ``config.role_tiers``.
        investigation_id: Scope for the DispatchCall event.
        max_tokens: Override the tier's default if provided.
        verification_required: Stamped onto the event for downstream
            audit; routing is unaffected today (verification re-dispatch
            is a separate concern).
        context_pack_event_id: Optional pointer to the
            CONTEXT_PACK_ASSEMBLED event that produced this prompt's
            context layers. Recorded on DispatchCall so a query can
            answer "what did the model see when it made this call."
        parent_event_id: Optional parent for the DispatchCall event.
        config: Pre-loaded DispatchConfig (preferred). For tests.
        config_path: Path to a config.yaml. Used when ``config`` is None.
            Defaults to ``substrate/dispatch/config.yaml`` co-located
            with this module.
        provider_override: SPR-01 M3 — when set (together with
            ``model_override``), swap the PRIMARY tier's
            ``(provider, model)`` for this one. The fallback chain is
            preserved unchanged, so the override is a preference, not a
            single point of failure: if the override provider is down or
            unregistered, the call falls through to the config's fallback
            exactly as a normal primary failure would. This is how the
            curated fast/deep research tier
            (``substrate/dispatch/research_tier.py``) makes the selection
            actually change which provider is routed to — NOT a second
            dispatcher (§16), just a per-call primary swap on the one
            Hermes-routed path. Ignored unless BOTH override args are
            present (a half-specified override is a caller bug, so we
            refuse to guess the missing half and fall back to config).
        model_override: see ``provider_override``.
        latency_mode: ``interactive`` or ``autonomous``. When set (or when
            ``ANTIEK_LATENCY_MODE`` / ``engagement_policy.default_mode`` apply),
            ``engagement_policy.role_tier_overrides`` remap roles before tier
            lookup — e.g. interactive driving roles → ``speed`` (TileRT).
        brain: ``glm`` (default, TileRT when engaged) or ``premium`` (Opus/pro
            driving tiers). See ``brain_choice.py``.
        deliverable_speed_preference: when autonomous, still route driving
            roles through interactive overrides if the user asked for speed
            on this deliverable.

    Returns:
        DispatchResult for the first successful call.

    Raises:
        ProviderError: if every tier in the fallback chain failed.
        KeyError: if the role is not in ``config.role_tiers`` or the tier
            is not in ``config.tiers``.
    """
    if config is None:
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        config = DispatchConfig.from_yaml(config_path)

    if role not in config.role_tiers:
        raise KeyError(
            f"Role {role!r} not in config.role_tiers. Known: "
            f"{sorted(config.role_tiers)}"
        )
    base_tier = config.role_tiers[role]
    mode = resolve_latency_mode(
        latency_mode,  # type: ignore[arg-type]
        policy=config.engagement_policy,
    )
    tier_name = resolve_tier_name(
        role,
        base_tier,
        mode=mode,
        policy=config.engagement_policy,
        brain=brain,  # type: ignore[arg-type]
        deliverable_speed_preference=deliverable_speed_preference,
    )
    if tier_name not in config.tiers:
        raise KeyError(
            f"Tier {tier_name!r} (for role {role!r}) not in config.tiers. Known: "
            f"{sorted(config.tiers)}"
        )

    prompt_hash = _sha256_prefix(prompt)
    tier = config.tiers[tier_name]
    # SPR-01 M3 route-override: swap ONLY the primary's (provider, model),
    # keeping the same pricing/limits and the SAME fallback chain. Requires
    # both halves; a partial override is ignored (refuse to guess).
    if provider_override and model_override:
        tier = TierConfig(
            name=tier.name,
            provider=provider_override,
            model=model_override,
            max_tokens=tier.max_tokens,
            temperature=tier.temperature,
            context_budget_tokens=tier.context_budget_tokens,
            pricing=tier.pricing,
            fallback=tier.fallback,
        )
    chain_index = 0
    last_error: ProviderError | None = None

    current: TierConfig | None = tier
    while current is not None:
        if current.provider is None or current.model is None:
            # Tier defined but no concrete backend (e.g. "local" placeholder).
            # Skip to fallback.
            current = current.fallback
            chain_index += 1
            continue

        # An unregistered provider (e.g. a route-override pointing at a
        # provider whose API key isn't set, so bootstrap never registered
        # it) is a recoverable, fallback-triggering condition — NOT a hard
        # crash of the whole dispatch. Convert the registry KeyError into a
        # retryable ProviderError so the same fallback machinery below
        # handles it. This is what keeps the SPR-01 M3 route-override a
        # preference, not a single point of failure.
        try:
            provider = get_provider(current.provider)
        except KeyError as e:
            last_error = ProviderError(
                f"provider {current.provider!r} is not registered "
                f"(no API key / not bootstrapped); falling back. {e}",
                provider=current.provider, model=current.model or "<none>",
                latency_ms=0, retryable=True,
            )
            _emit_dispatch_call(
                investigation_id=investigation_id,
                parent_event_id=parent_event_id,
                role=role,
                tier=tier_name,
                provider=current.provider,
                model=current.model,
                usage=NormalizedUsage(input_tokens=0, output_tokens=0),
                cost_usd=0.0,
                latency_ms=0,
                verification_required=verification_required,
                fallback_chain_index=chain_index,
                prompt_hash=prompt_hash,
                finish_reason="error",
                context_pack_event_id=context_pack_event_id,
            )
            current = current.fallback
            chain_index += 1
            continue
        effective_max_tokens = max_tokens if max_tokens is not None else current.max_tokens

        t_start = time.monotonic()
        try:
            raw = provider.call(
                model=current.model,
                prompt=prompt,
                max_tokens=effective_max_tokens,
                temperature=current.temperature,
            )
        except ProviderError as e:
            # Emit a failure event so the error is queryable too. Use the
            # latency the provider reported on the exception if available.
            latency_ms = e.latency_ms or int((time.monotonic() - t_start) * 1000)
            _emit_dispatch_call(
                investigation_id=investigation_id,
                parent_event_id=parent_event_id,
                role=role,
                tier=tier_name,
                provider=current.provider,
                model=current.model,
                usage=NormalizedUsage(input_tokens=0, output_tokens=0),
                cost_usd=0.0,
                latency_ms=latency_ms,
                verification_required=verification_required,
                fallback_chain_index=chain_index,
                prompt_hash=prompt_hash,
                finish_reason="error",
                context_pack_event_id=context_pack_event_id,
            )
            last_error = e
            current = current.fallback
            chain_index += 1
            continue

        # Success: normalize, cost, emit, return.
        usage = provider.normalize_usage(raw.raw_usage)
        finish = normalize_finish_reason(raw.finish_reason)
        cost = _compute_cost_usd(usage, current.pricing)
        eid = _emit_dispatch_call(
            investigation_id=investigation_id,
            parent_event_id=parent_event_id,
            role=role,
            tier=tier_name,
            provider=current.provider,
            model=current.model,
            usage=usage,
            cost_usd=cost,
            latency_ms=raw.latency_ms,
            verification_required=verification_required,
            fallback_chain_index=chain_index,
            prompt_hash=prompt_hash,
            finish_reason=finish,
            context_pack_event_id=context_pack_event_id,
        )
        return DispatchResult(
            text=raw.text,
            usage=usage,
            cost_usd=cost,
            latency_ms=raw.latency_ms,
            provider=current.provider,
            model=current.model,
            tier=tier_name,
            finish_reason=finish,
            fallback_chain_index=chain_index,
            event_id=eid,
        )

    # All tiers exhausted.
    if last_error is None:
        raise ProviderError(
            f"No usable backend for role {role!r} (tier {tier_name!r}); "
            "every tier in the chain has provider=None.",
            provider="<none>", model="<none>", latency_ms=0,
        )
    raise last_error
