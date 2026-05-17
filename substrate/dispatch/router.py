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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml  # type: ignore[import]

# Package-relative imports with a fall-back for direct-script execution.
try:
    from ..event_log import emit_typed
    from ..schemas import DispatchCallPayload
    from .base import (
        NormalizedUsage,
        Provider,
        ProviderError,
        RawProviderResponse,
    )
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from event_log import emit_typed  # type: ignore[no-redef]
    from schemas import DispatchCallPayload  # type: ignore[no-redef]
    from dispatch.base import (  # type: ignore[no-redef]
        NormalizedUsage,
        Provider,
        ProviderError,
        RawProviderResponse,
    )


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
    provider: Optional[str]
    model: Optional[str]
    max_tokens: int
    temperature: float
    context_budget_tokens: int
    pricing: TierPricing = field(default_factory=TierPricing)
    fallback: Optional["TierConfig"] = None


@dataclass(frozen=True)
class DispatchConfig:
    """Loaded ``config.yaml``. Use ``DispatchConfig.from_yaml(path)`` or
    construct directly for tests."""

    role_tiers: Mapping[str, str]  # role name → tier name
    tiers: Mapping[str, TierConfig]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DispatchConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: Mapping[str, Any]) -> "DispatchConfig":
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
            fallback_obj: Optional[TierConfig] = None
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

        return cls(role_tiers=data.get("role_tiers", {}), tiers=resolved)


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
    finish_reason: Optional[str]
    fallback_chain_index: int  # 0 = primary, 1 = first fallback, etc.
    event_id: Optional[str]  # the DispatchCall event_id for this success


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_prefix(s: str, n: int = 12) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def _compute_cost_usd(usage: NormalizedUsage, pricing: TierPricing) -> float:
    """One place computes cost. Adapters do not."""
    paid_input = max(0, usage.input_tokens - usage.cached_input_tokens)
    return (
        (paid_input / 1_000_000.0) * pricing.input_per_mtok
        + (usage.cached_input_tokens / 1_000_000.0) * pricing.cached_input_per_mtok
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


def normalize_finish_reason(provider_native: Optional[str]) -> Optional[str]:
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
    parent_event_id: Optional[str],
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
    finish_reason: Optional[str],
    context_pack_event_id: Optional[str],
) -> Optional[str]:
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
    max_tokens: Optional[int] = None,
    verification_required: bool = False,
    context_pack_event_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    config: Optional[DispatchConfig] = None,
    config_path: Optional[str | Path] = None,
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
    tier_name = config.role_tiers[role]
    if tier_name not in config.tiers:
        raise KeyError(
            f"Tier {tier_name!r} (for role {role!r}) not in config.tiers. Known: "
            f"{sorted(config.tiers)}"
        )

    prompt_hash = _sha256_prefix(prompt)
    tier = config.tiers[tier_name]
    chain_index = 0
    last_error: Optional[ProviderError] = None

    current: Optional[TierConfig] = tier
    while current is not None:
        if current.provider is None or current.model is None:
            # Tier defined but no concrete backend (e.g. "local" placeholder).
            # Skip to fallback.
            current = current.fallback
            chain_index += 1
            continue

        provider = get_provider(current.provider)
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
