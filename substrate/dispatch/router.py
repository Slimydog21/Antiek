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
import importlib
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Package-relative imports with a fall-back for direct-script execution.
try:
    from ..event_log import emit_typed, trajectory
    from ..schemas import DispatchCallPayload
    from .base import (
        NormalizedUsage,
        Provider,
        ProviderError,
    )
    from .breaker import default_breaker
    from .research_tier import RESEARCH_TIERS, resolve_research_tier
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from dispatch.base import (  # type: ignore[import-not-found, no-redef]
        NormalizedUsage,
        Provider,
        ProviderError,
    )
    from dispatch.breaker import default_breaker  # type: ignore[import-not-found, no-redef]
    from dispatch.research_tier import (  # type: ignore[import-not-found, no-redef]
        RESEARCH_TIERS,
        resolve_research_tier,
    )
    from event_log import (  # type: ignore[import-not-found, no-redef]
        emit_typed,
        trajectory,
    )
    from schemas import DispatchCallPayload  # type: ignore[import-not-found, no-redef]


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


def _fallback_tier_config(
    tier_name: str,
    fb: Mapping[str, Any],
    base: TierConfig,
    *,
    depth: int = 1,
) -> TierConfig:
    """Build a (possibly multi-layer) fallback TierConfig from an inline
    YAML ``fallback`` dict. Recurses when the dict carries its own nested
    ``fallback`` key, so a tier may declare a chain of any depth:

        fallback:
          provider: deepseek
          model: deepseek-v4-pro
          fallback:
            provider: xiaomi
            model: mimo-v2.5-pro

    The router's dispatch walker already follows ``tier.fallback`` to None,
    so this helper is the only place that needed to learn recursion. All
    layers inherit the base tier's pricing / token / temperature defaults —
    a fallback is a liveness mechanism, not a separate pricing tier. depth=1
    reproduces the legacy single-fallback name ``<tier>__fallback`` exactly.
    """
    nested = (
        _fallback_tier_config(tier_name, fb["fallback"], base, depth=depth + 1)
        if isinstance(fb.get("fallback"), dict)
        else None
    )
    suffix = "" if depth == 1 else str(depth)
    return TierConfig(
        name=f"{tier_name}__fallback{suffix}",
        provider=fb.get("provider"),
        model=fb.get("model"),
        max_tokens=base.max_tokens,
        temperature=base.temperature,
        context_budget_tokens=base.context_budget_tokens,
        pricing=base.pricing,
        fallback=nested,
    )


@dataclass(frozen=True)
class DispatchConfig:
    """Loaded ``config.yaml``. Use ``DispatchConfig.from_yaml(path)`` or
    construct directly for tests."""

    role_tiers: Mapping[str, str]  # role name → tier name
    tiers: Mapping[str, TierConfig]

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
                # Recursive: a nested ``fallback`` key declares a deeper
                # link (GLM → DeepSeek → MiMo). Single-layer tiers (no
                # nested key) behave exactly as before.
                fallback_obj = _fallback_tier_config(tier_name, fb, base)
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


def _consume_nd_decision(*, scope: object | None = None) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    int | None,
    bool,
    str | None,
]:
    """Drain ND attribution lazily to avoid dispatch package import cycles.

    Returns an explicit 7-tuple so DispatchCallPayload construction stays
    mypy-strict (``**dict`` unpacking produced NEW mypy:arg-type on CI).
    """
    try:
        module = importlib.import_module(".nd_attribution", package=__package__)
    except ImportError:  # pragma: no cover
        module = importlib.import_module("dispatch.nd_attribution")
    consume_nd_decision = module.consume_nd_decision
    nd = dict(consume_nd_decision(scope=scope))
    latency = nd.get("nd_decision_latency_ms")
    latency_ms: int | None = None if latency is None else int(latency)
    return (
        str(nd["nd_session_id"]) if nd.get("nd_session_id") is not None else None,
        str(nd["nd_recommended_provider"])
        if nd.get("nd_recommended_provider") is not None
        else None,
        str(nd["nd_recommended_model"])
        if nd.get("nd_recommended_model") is not None
        else None,
        str(nd["nd_tradeoff"]) if nd.get("nd_tradeoff") is not None else None,
        latency_ms,
        bool(nd.get("nd_bypassed", False)),
        str(nd["nd_bypass_reason"]) if nd.get("nd_bypass_reason") is not None else None,
    )


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
    nd_scope: object | None = None,
) -> str | None:
    """Emit one DispatchCall event. Returns the event_id."""
    (
        nd_session_id,
        nd_recommended_provider,
        nd_recommended_model,
        nd_tradeoff,
        nd_decision_latency_ms,
        nd_bypassed,
        nd_bypass_reason,
    ) = _consume_nd_decision(scope=nd_scope)
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
            nd_session_id=nd_session_id,
            nd_recommended_provider=nd_recommended_provider,
            nd_recommended_model=nd_recommended_model,
            nd_tradeoff=nd_tradeoff,
            nd_decision_latency_ms=nd_decision_latency_ms,
            nd_bypassed=nd_bypassed,
            nd_bypass_reason=nd_bypass_reason,
        ),
        parent_event_id=parent_event_id,
        role=role,
        policy_id=f"{provider}/{model}",
    )


def _dispatch_authoritative(
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
    nd_scope: object | None = None,
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
    tier = _override_primary(
        config.tiers[tier_name], provider_override, model_override
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
        # mypy --strict: bind the guard-narrowed fields once. TierConfig's
        # provider/model are Optional by design (placeholder tiers), and
        # attribute narrowing does not survive the calls below.
        provider_name: str = current.provider
        model_name: str = current.model


        # An unregistered provider (e.g. a route-override pointing at a
        # provider whose API key isn't set, so bootstrap never registered
        # it) is a recoverable, fallback-triggering condition — NOT a hard
        # crash of the whole dispatch. Convert the registry KeyError into a
        # retryable ProviderError so the same fallback machinery below
        # handles it. This is what keeps the SPR-01 M3 route-override a
        # preference, not a single point of failure.
        try:
            provider = get_provider(provider_name)
        except KeyError as e:
            last_error = ProviderError(
                f"provider {provider_name!r} is not registered "
                f"(no API key / not bootstrapped); falling back. {e}",
                provider=provider_name, model=model_name or "<none>",
                latency_ms=0, retryable=True,
            )
            _emit_dispatch_call(
                investigation_id=investigation_id,
                parent_event_id=parent_event_id,
                role=role,
                tier=tier_name,
                provider=provider_name,
                model=model_name,
                usage=NormalizedUsage(input_tokens=0, output_tokens=0),
                cost_usd=0.0,
                latency_ms=0,
                verification_required=verification_required,
                fallback_chain_index=chain_index,
                prompt_hash=prompt_hash,
                finish_reason="error",
                context_pack_event_id=context_pack_event_id,
                nd_scope=nd_scope,
            )
            current = current.fallback
            chain_index += 1
            continue
        # Circuit breaker (SPR-04): a provider whose breaker is OPEN is skipped
        # fast and the tier-fallback chain carries the call — the same
        # "skip + fall through" mechanism the unregistered/no-key path uses
        # above. No retry (I-NORETRY); the breaker only decides whether to call.
        if default_breaker.is_open(provider_name):
            last_error = ProviderError(
                f"provider {provider_name!r} circuit breaker is OPEN "
                "(recent infra failures); skipping and falling back.",
                provider=provider_name, model=model_name or "<none>",
                latency_ms=0, retryable=True,
            )
            _emit_dispatch_call(
                investigation_id=investigation_id,
                parent_event_id=parent_event_id,
                role=role,
                tier=tier_name,
                provider=provider_name,
                model=model_name,
                usage=NormalizedUsage(input_tokens=0, output_tokens=0),
                cost_usd=0.0,
                latency_ms=0,
                verification_required=verification_required,
                fallback_chain_index=chain_index,
                prompt_hash=prompt_hash,
                finish_reason="error",
                context_pack_event_id=context_pack_event_id,
                nd_scope=nd_scope,
            )
            current = current.fallback
            chain_index += 1
            continue

        effective_max_tokens = max_tokens if max_tokens is not None else current.max_tokens

        t_start = time.monotonic()
        try:
            raw = provider.call(
                model=model_name,
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
                provider=provider_name,
                model=model_name,
                usage=NormalizedUsage(input_tokens=0, output_tokens=0),
                cost_usd=0.0,
                latency_ms=latency_ms,
                verification_required=verification_required,
                fallback_chain_index=chain_index,
                prompt_hash=prompt_hash,
                finish_reason="error",
                context_pack_event_id=context_pack_event_id,
                nd_scope=nd_scope,
            )
            # Count this genuine provider-call failure toward the breaker. Config
            # conditions (unregistered/no-key) never reach here — they fall
            # through at get_provider above — so every failure counted is real.
            default_breaker.record_failure(provider_name)
            last_error = e
            current = current.fallback
            chain_index += 1
            continue

        # Success: normalize, cost, emit, return.
        default_breaker.record_success(provider_name)
        usage = provider.normalize_usage(raw.raw_usage)
        finish = normalize_finish_reason(raw.finish_reason)
        cost = _compute_cost_usd(usage, current.pricing)
        eid = _emit_dispatch_call(
            investigation_id=investigation_id,
            parent_event_id=parent_event_id,
            role=role,
            tier=tier_name,
            provider=provider_name,
            model=model_name,
            usage=usage,
            cost_usd=cost,
            latency_ms=raw.latency_ms,
            verification_required=verification_required,
            fallback_chain_index=chain_index,
            prompt_hash=prompt_hash,
            finish_reason=finish,
            context_pack_event_id=context_pack_event_id,
            nd_scope=nd_scope,
        )
        return DispatchResult(
            text=raw.text,
            usage=usage,
            cost_usd=cost,
            latency_ms=raw.latency_ms,
            provider=provider_name,
            model=model_name,
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


def _tier_candidates(tier: TierConfig) -> tuple[str, ...]:
    candidates: list[str] = []
    current: TierConfig | None = tier
    while current is not None:
        if current.provider is not None and current.model is not None:
            candidate = f"{current.provider}/{current.model}"
            if candidate not in candidates:
                candidates.append(candidate)
        current = current.fallback
    return tuple(candidates)


def _override_primary(
    tier: TierConfig, provider_override: str | None, model_override: str | None
) -> TierConfig:
    if not provider_override or not model_override:
        return tier
    return TierConfig(
        name=tier.name,
        provider=provider_override,
        model=model_override,
        max_tokens=tier.max_tokens,
        temperature=tier.temperature,
        context_budget_tokens=tier.context_budget_tokens,
        pricing=tier.pricing,
        fallback=tier.fallback,
    )


# The four Loop 1 roles that mine and structure evidence before synthesis.
# Synthesis is deliberately absent: its voice has an independent config pin
# guarded by interfaces.research.api.synthesizer._research_tier_override.
_RESEARCH_TIER_ROLES = frozenset(
    {"decomposer", "evidence_retriever", "parameter_extractor", "connector"}
)


def _recorded_research_tier_override(
    investigation_id: str,
    role: str,
) -> tuple[str | None, str | None]:
    """Resolve an explicit start-event tier for a Loop 1 research role.

    The start event is the durable authority for the operator's choice. No
    event, a legacy null, a malformed value, or a non-research role leaves the
    configured route untouched. This helper never invents the default: the
    API records a tier only when the operator explicitly selected one.
    """
    if role not in _RESEARCH_TIER_ROLES:
        return None, None
    try:
        rows = trajectory(investigation_id)
    except Exception:  # pragma: no cover - event diagnostics never break dispatch
        return None, None
    for row in rows:
        if row.get("action_type") != "investigation.start_requested":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None, None
        recorded = payload.get("research_tier")
        if recorded not in RESEARCH_TIERS:
            return None, None
        target = resolve_research_tier(recorded)
        return target.provider, target.model
    return None, None


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
) -> DispatchResult:
    """Evaluate optional ND shadow evidence, then run authoritative dispatch unchanged."""
    # Explicit call-site overrides remain strongest. Otherwise, Loop 1's
    # research roles consume the tier persisted by POST /investigations.
    # This is the missing map→execution wire; it is intentionally centralized
    # so every role uses one resolver and synthesis cannot accidentally opt in.
    if provider_override is None and model_override is None:
        provider_override, model_override = _recorded_research_tier_override(
            investigation_id,
            role,
        )
    if config is None:
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        config = DispatchConfig.from_yaml(config_path)

    attribution_tokens: tuple[Any, Any, Any] | None = None
    nd_scope = object()
    tier_name = config.role_tiers.get(role)
    tier = config.tiers.get(tier_name) if tier_name is not None else None
    if tier is not None:
        try:
            attribution_module = importlib.import_module(".nd_attribution", package=__package__)
            shadow_module = importlib.import_module(".notdiamond_shadow", package=__package__)
        except (ImportError, TypeError):  # pragma: no cover
            attribution_module = importlib.import_module("dispatch.nd_attribution")
            try:
                shadow_module = importlib.import_module("dispatch.notdiamond_shadow")
            except ImportError:
                shadow_module = None

        attribution = None if shadow_module is None else shadow_module.evaluate_notdiamond_shadow(
            prompt=prompt,
            role=role,
            candidates=_tier_candidates(
                _override_primary(tier, provider_override, model_override)
            ),
        )
        if attribution is not None:
            attribution_tokens = attribution_module.push_nd_decision(
                {
                    "nd_session_id": attribution.session_id,
                    "nd_recommended_provider": attribution.recommended_provider,
                    "nd_recommended_model": attribution.recommended_model,
                    "nd_tradeoff": attribution.tradeoff,
                    "nd_decision_latency_ms": attribution.decision_latency_ms,
                    "nd_bypassed": True,
                    "nd_bypass_reason": attribution.bypass_reason,
                },
                scope=nd_scope,
            )
    try:
        return _dispatch_authoritative(
            prompt,
            role,
            investigation_id=investigation_id,
            max_tokens=max_tokens,
            verification_required=verification_required,
            context_pack_event_id=context_pack_event_id,
            parent_event_id=parent_event_id,
            config=config,
            provider_override=provider_override,
            model_override=model_override,
            nd_scope=nd_scope,
        )
    finally:
        if attribution_tokens is not None:
            attribution_module.reset_nd_decision(attribution_tokens)
