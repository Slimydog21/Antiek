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
import json
import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# Package-relative imports with a fall-back for direct-script execution.
try:
    from ..event_log import (
        IdempotencyConflict,
        ResearchBudgetExceeded,
        ResearchBudgetLedgerInvalid,
        append_event_once_authorized,
        current_investigation_authority,
        current_investigation_execution,
        emit_typed,
        prepare_typed_event,
        release_research_call_authorized,
        research_call_dispatch_event_id,
        reserve_research_call_authorized,
        settle_research_call_authorized,
        trajectory_authorized_append_order,
    )
    from ..schemas import (
        DispatchCallPayload,
        Event,
        ResearchCallReleasedPayload,
        ResearchCallReservedPayload,
        ResearchCallSettledPayload,
    )
    from .base import (
        IdempotentProvider,
        NormalizedUsage,
        Provider,
        ProviderCallNotAttempted,
        ProviderError,
    )
    from .breaker import default_breaker
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from dispatch.base import (  # type: ignore[import-not-found, no-redef]
        IdempotentProvider,
        NormalizedUsage,
        Provider,
        ProviderCallNotAttempted,
        ProviderError,
    )
    from dispatch.breaker import default_breaker  # type: ignore[import-not-found, no-redef]
    from event_log import (  # type: ignore[import-not-found, no-redef]
        IdempotencyConflict,
        ResearchBudgetExceeded,
        ResearchBudgetLedgerInvalid,
        append_event_once_authorized,
        current_investigation_authority,
        current_investigation_execution,
        emit_typed,
        prepare_typed_event,
        release_research_call_authorized,
        reserve_research_call_authorized,
        settle_research_call_authorized,
        trajectory_authorized_append_order,
    )
    from schemas import (  # type: ignore[import-not-found, no-redef]
        DispatchCallPayload,
        Event,
        ResearchCallReleasedPayload,
        ResearchCallReservedPayload,
        ResearchCallSettledPayload,
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
    currency: str | None = None
    billing_unit: str | None = None
    source_url: str | None = None
    verified_at: str | None = None
    expires_at: str | None = None


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


def pricing_from_mapping(raw: Any) -> TierPricing:
    """Parse one route's own pricing; absence means unknown, never inherited."""
    pricing = raw if isinstance(raw, Mapping) else {}
    return TierPricing(
        input_per_mtok=pricing.get("input_per_mtok", 0.0),
        output_per_mtok=pricing.get("output_per_mtok", 0.0),
        cached_input_per_mtok=pricing.get("cached_input_per_mtok", 0.0),
        currency=pricing.get("currency"),
        billing_unit=pricing.get("billing_unit"),
        source_url=pricing.get("source_url"),
        verified_at=pricing.get("verified_at"),
        expires_at=pricing.get("expires_at"),
    )


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
    Layers inherit token and temperature limits, but never pricing: a fallback
    is a distinct provider/model billing route. Missing inline pricing remains
    unknown so authenticated interactive dispatch fails closed. depth=1
    preserves the legacy single-fallback name ``<tier>__fallback`` exactly.
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
        pricing=pricing_from_mapping(fb.get("pricing")),
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
            tiers[tier_name] = TierConfig(
                name=tier_name,
                provider=tier_data.get("provider"),
                model=tier_data.get("model"),
                max_tokens=defaults.get("max_tokens", 4096),
                temperature=defaults.get("temperature", 0.2),
                context_budget_tokens=defaults.get("context_budget_tokens", 32000),
                pricing=pricing_from_mapping(tier_data.get("pricing")),
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


def _canonical_sha256(domain: str, value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("utf-8") + b"\x00" + encoded).hexdigest()


def pricing_authority(
    *,
    provider: str | None,
    model: str | None,
    pricing: TierPricing,
    now: datetime | None = None,
) -> tuple[bool, str | None, str]:
    """Validate and fingerprint one exact route's price authority.

    The fingerprint is returned even for unavailable authority so Settings can
    invalidate stale generations without exposing or inventing a usable price.
    """
    raw_rates = (
        pricing.input_per_mtok,
        pricing.output_per_mtok,
        pricing.cached_input_per_mtok,
    )
    rates_valid = all(
        isinstance(rate, (int, float))
        and not isinstance(rate, bool)
        and math.isfinite(float(rate))
        and float(rate) >= 0
        for rate in raw_rates
    )
    normalized_rates = (
        tuple(float(rate) for rate in raw_rates)
        if rates_valid
        else tuple(repr(rate) for rate in raw_rates)
    )

    verified: datetime | None = None
    expires: datetime | None = None
    timestamps_valid = False
    if isinstance(pricing.verified_at, str) and isinstance(pricing.expires_at, str):
        try:
            verified = datetime.fromisoformat(pricing.verified_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(pricing.expires_at.replace("Z", "+00:00"))
            timestamps_valid = verified.tzinfo is not None and expires.tzinfo is not None
        except ValueError:
            pass

    def canonical_time(value: datetime | None, raw: Any) -> str:
        if value is None or value.tzinfo is None:
            return repr(raw)
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def safe_text(value: Any) -> str | None:
        return value if isinstance(value, str) or value is None else repr(value)

    envelope = {
        "provider": safe_text(provider),
        "model": safe_text(model),
        "input_per_mtok": normalized_rates[0],
        "output_per_mtok": normalized_rates[1],
        "cached_input_per_mtok": normalized_rates[2],
        "currency": safe_text(pricing.currency),
        "billing_unit": safe_text(pricing.billing_unit),
        "source_url": safe_text(pricing.source_url),
        "verified_at": canonical_time(verified, pricing.verified_at),
        "expires_at": canonical_time(expires, pricing.expires_at),
    }
    fingerprint = _canonical_sha256("antiek.pricing-authority.v1", envelope)
    if not provider or not model:
        return False, "pricing route identity is incomplete", fingerprint
    if not rates_valid:
        return False, "pricing rates must be finite and non-negative", fingerprint
    input_rate, output_rate, _ = normalized_rates
    if input_rate <= 0 or output_rate <= 0:
        return False, "pricing rates are unknown", fingerprint
    if pricing.currency != "USD" or pricing.billing_unit != "per_million_tokens":
        return False, "pricing billing authority is unsupported", fingerprint
    if not isinstance(pricing.source_url, str) or not pricing.source_url.startswith(
        "https://"
    ):
        return False, "pricing source must be an authoritative HTTPS URL", fingerprint
    if not timestamps_valid or verified is None or expires is None:
        return False, "pricing verification window is malformed", fingerprint
    if expires <= verified:
        return False, "pricing verification window is invalid", fingerprint
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    if instant < verified or instant >= expires:
        return False, "pricing authority is not currently valid", fingerprint
    return True, None, fingerprint


def _projected_route_max_usd(
    prompt: str, tier: TierConfig, *, max_tokens: int
) -> float:
    """Conservative pre-call maximum using UTF-8 bytes as input-token cap."""
    pricing = tier.pricing
    pricing_valid, pricing_reason, _ = pricing_authority(
        provider=tier.provider,
        model=tier.model,
        pricing=pricing,
    )
    if not pricing_valid:
        raise ProviderCallNotAttempted(
            f"interactive research pricing authority unavailable: {pricing_reason}; "
            "provider call refused",
            provider=tier.provider or "<none>",
            model=tier.model or "<none>",
            latency_ms=0,
            retryable=False,
        )
    input_rate = max(
        pricing.input_per_mtok,
        pricing.cached_input_per_mtok,
        pricing.input_per_mtok * _CACHE_WRITE_MULTIPLIER,
    )
    dollars = (
        len(prompt.encode("utf-8")) * input_rate
        + max_tokens * pricing.output_per_mtok
    ) / 1_000_000.0
    # Eight-decimal upward rounding preserves sub-cent precision without ever
    # rounding a positive route projection down to zero.
    return max(0.00000001, math.ceil(dollars * 100_000_000) / 100_000_000)


@dataclass(frozen=True)
class _InteractiveBudgetCall:
    authority: Any
    reservation: ResearchCallReservedPayload
    reservation_event: Event
    provider_idempotency_key: str
    terminal: Event | None
    pricing: TierPricing
    temperature: float
    context_budget_tokens: int


def _interactive_budget_terminal(authority: Any, reservation_id: str) -> Event | None:
    terminal_rows = [
        row
        for row in trajectory_authorized_append_order(authority)
        if row.get("action_type")
        in {
            "research.call_settled",
            "research.call_released",
        }
        and (row.get("payload") or {}).get("reservation_id") == reservation_id
    ]
    if len(terminal_rows) > 1:
        raise ValueError("research reservation has multiple terminal receipts")
    return Event.model_validate(terminal_rows[0]) if terminal_rows else None


def _accepted_research_routes(
    authority: Any,
    *,
    role: str,
) -> tuple[tuple[Any, ...], str, str]:
    """Resolve the executable route chain from the accepted start manifest."""
    starts = [
        Event.model_validate(row)
        for row in trajectory_authorized_append_order(authority)
        if row.get("action_type") == "investigation.start_requested"
    ]
    if len(starts) != 1:
        raise ResearchBudgetLedgerInvalid(
            "research dispatch requires exactly one start authority"
        )
    start = starts[0].payload
    quote_id = getattr(start, "research_quote_id", None)
    manifest_fingerprint = getattr(
        start, "research_route_manifest_fingerprint", None
    )
    manifest = getattr(start, "research_route_manifest", None)
    if not quote_id or not manifest_fingerprint or not manifest:
        raise ResearchBudgetLedgerInvalid(
            "research dispatch requires accepted quote authority"
        )
    matches = sorted(
        (row for row in manifest if row.role == role),
        key=lambda row: row.fallback_index,
    )
    selected_role = getattr(start, "selected_driver_role", None)
    if selected_role == role:
        exact = [
            row
            for row in matches
            if row.provider == getattr(start, "selected_driver_provider", None)
            and row.model == getattr(start, "selected_driver_model", None)
            and row.pricing_fingerprint
            == getattr(start, "selected_driver_pricing_fingerprint", None)
        ]
        if len(exact) != 1:
            raise ResearchBudgetLedgerInvalid(
                "accepted exact driver is unavailable in the quoted manifest"
            )
        matches = [exact[0].model_copy(update={"fallback_index": 0})]
    if not matches or [row.fallback_index for row in matches] != list(
        range(len(matches))
    ):
        raise ResearchBudgetLedgerInvalid(
            "accepted quote has no canonical route chain for dispatch"
        )
    return tuple(matches), quote_id, manifest_fingerprint


def _tier_from_accepted_route(accepted: Any, fallback: TierConfig | None) -> TierConfig:
    return TierConfig(
        name=accepted.route_tier_name,
        provider=accepted.provider,
        model=accepted.model,
        max_tokens=accepted.max_output_tokens,
        temperature=accepted.temperature,
        context_budget_tokens=accepted.context_budget_tokens,
        pricing=TierPricing(
            input_per_mtok=accepted.input_per_mtok,
            output_per_mtok=accepted.output_per_mtok,
            cached_input_per_mtok=accepted.cached_input_per_mtok,
            currency=accepted.currency,
            billing_unit=accepted.billing_unit,
            source_url=accepted.source_url,
            verified_at=accepted.verified_at,
            expires_at=accepted.expires_at,
        ),
        fallback=fallback,
    )


def _accepted_tier_chain(authority: Any, *, role: str) -> tuple[TierConfig, str, str]:
    rows, quote_id, fingerprint = _accepted_research_routes(authority, role=role)
    chain: TierConfig | None = None
    for row in reversed(rows):
        chain = _tier_from_accepted_route(row, chain)
    if chain is None:  # pragma: no cover - guarded by _accepted_research_routes
        raise ResearchBudgetLedgerInvalid("accepted quote route chain is empty")
    return chain, quote_id, fingerprint


def _prepare_interactive_budget_call(
    *,
    authority: Any,
    prompt: str,
    prompt_hash: str,
    role: str,
    tier_name: str,
    route: TierConfig,
    fallback_chain_index: int,
    max_tokens: int,
    verification_required: bool,
    context_pack_event_id: str | None,
    parent_event_id: str | None,
) -> _InteractiveBudgetCall:
    provider = route.provider
    model = route.model
    if provider is None or model is None:
        raise ValueError("interactive budget call requires a concrete route")
    rows, research_quote_id, manifest_fingerprint = _accepted_research_routes(
        authority, role=role
    )
    if fallback_chain_index >= len(rows):
        raise ResearchBudgetLedgerInvalid("accepted quote route index is unavailable")
    accepted = rows[fallback_chain_index]
    if (
        provider != accepted.provider
        or model != accepted.model
        or route.name != accepted.route_tier_name
        or max_tokens != accepted.max_output_tokens
    ):
        raise ResearchBudgetLedgerInvalid(
            "dispatch route differs from accepted quote execution plan"
        )
    accepted_route = _tier_from_accepted_route(accepted, None)
    accepted_pricing = accepted_route.pricing
    operation = {
        "investigation_id": authority.investigation_id,
        "stream_key": authority.stream_key,
        "parent_event_id": parent_event_id,
        "role": role,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "fallback_chain_index": fallback_chain_index,
        "max_tokens": max_tokens,
        "verification_required": verification_required,
        "context_pack_event_id": context_pack_event_id,
    }
    operation_sha256 = _canonical_sha256("antiek.research-call.operation.v1", operation)
    request = {
        **operation,
        "provider": provider,
        "model": model,
        "tier": tier_name,
        "temperature": accepted_route.temperature,
        "context_budget_tokens": accepted_route.context_budget_tokens,
        "pricing": {
            "input_per_mtok": accepted_pricing.input_per_mtok,
            "output_per_mtok": accepted_pricing.output_per_mtok,
            "cached_input_per_mtok": accepted_pricing.cached_input_per_mtok,
        },
    }
    request_sha256 = _canonical_sha256("antiek.research-call.request.v1", request)
    provider_key = "antiek-research-v1-" + _canonical_sha256(
        "antiek.research-call.provider-key.v1",
        {
            "stream_key": authority.stream_key,
            "operation_sha256": operation_sha256,
            "request_sha256": request_sha256,
        },
    )
    reservation = ResearchCallReservedPayload(
        reservation_id=f"res-{operation_sha256}",
        request_sha256=request_sha256,
        target_role=role,
        tier=tier_name,  # type: ignore[arg-type]
        provider=provider,
        model=model,
        route_tier_name=accepted.route_tier_name,
        fallback_chain_index=fallback_chain_index,
        prompt_hash=prompt_hash,
        max_tokens=max_tokens,
        temperature=accepted.temperature,
        context_budget_tokens=accepted.context_budget_tokens,
        verification_required=verification_required,
        context_pack_event_id=context_pack_event_id,
        projected_max_cost_usd=_projected_route_max_usd(
            prompt, accepted_route, max_tokens=max_tokens
        ),
        provider_idempotency_key_sha256=hashlib.sha256(
            provider_key.encode("utf-8")
        ).hexdigest(),
        parent_request_event_id=parent_event_id,
        research_quote_id=research_quote_id,
        research_route_manifest_fingerprint=manifest_fingerprint,
        pricing_fingerprint=accepted.pricing_fingerprint,
    )
    reservation_event, _ = reserve_research_call_authorized(
        authority,
        reservation,
        role=role,
        policy_id=f"{provider}/{model}",
    )
    return _InteractiveBudgetCall(
        authority=authority,
        reservation=reservation,
        reservation_event=reservation_event,
        provider_idempotency_key=provider_key,
        terminal=_interactive_budget_terminal(authority, reservation.reservation_id),
        pricing=accepted_pricing,
        temperature=accepted.temperature,
        context_budget_tokens=accepted.context_budget_tokens,
    )


def _release_interactive_budget_call(
    budget_call: _InteractiveBudgetCall,
    *,
    reason: str,
    error: BaseException | None = None,
) -> None:
    release_research_call_authorized(
        budget_call.authority,
        ResearchCallReleasedPayload(
            reservation_id=budget_call.reservation.reservation_id,
            reservation_event_id=budget_call.reservation_event.event_id,
            request_sha256=budget_call.reservation.request_sha256,
            reason=reason,  # type: ignore[arg-type]
            error_sha256=(
                hashlib.sha256(
                    f"{type(error).__name__}:{error}".encode()
                ).hexdigest()
                if error is not None
                else None
            ),
        ),
        role=budget_call.reservation.target_role,
        policy_id=(
            f"{budget_call.reservation.provider}/{budget_call.reservation.model}"
        ),
    )


def _success_dispatch_event_authorized(
    budget_call: _InteractiveBudgetCall,
    payload: DispatchCallPayload,
    *,
    parent_event_id: str | None,
) -> Event:
    fence = current_investigation_execution(
        budget_call.authority.investigation_id
    )
    candidate = prepare_typed_event(
        budget_call.authority.investigation_id,
        payload,
        event_id=research_call_dispatch_event_id(
            budget_call.reservation_event.event_id
        ),
        parent_event_id=parent_event_id,
        role=budget_call.reservation.target_role,
        policy_id=(
            f"{budget_call.reservation.provider}/{budget_call.reservation.model}"
        ),
        execution_generation=fence[0] if fence is not None else None,
    )
    try:
        append_event_once_authorized(budget_call.authority, candidate)
        return candidate
    except ValueError:
        rows = [
            row
            for row in trajectory_authorized_append_order(budget_call.authority)
            if row.get("event_id") == candidate.event_id
        ]
        if len(rows) != 1:
            raise
        stored = Event.model_validate(rows[0])
        if not isinstance(stored.payload, DispatchCallPayload):
            raise
        candidate_core = payload.model_dump(mode="json", exclude={"latency_ms"})
        stored_core = stored.payload.model_dump(mode="json", exclude={"latency_ms"})
        if (
            candidate_core != stored_core
            or stored.parent_event_id != parent_event_id
            or stored.role != budget_call.reservation.target_role
            or stored.policy_id
            != f"{budget_call.reservation.provider}/{budget_call.reservation.model}"
        ):
            raise IdempotencyConflict(
                "provider replay conflicts with canonical dispatch receipt"
            ) from None
        return stored


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
    idempotency_key: str | None = None,
    allowed_routes: frozenset[str] | None = None,
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
        idempotency_key: Stable paid-operation key. When provided, the router
            refuses providers without ``IdempotentProvider`` support before
            network I/O and carries the key only in the transport header.
        allowed_routes: Optional closed ``provider/model`` set. Autonomous
            callers use this signed allowlist to block late registry changes
            before provider I/O.

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

    interactive_authority = current_investigation_authority(investigation_id)
    if interactive_authority is not None and idempotency_key is not None:
        raise ValueError(
            "authenticated interactive dispatch derives its idempotency key server-side"
        )
    if interactive_authority is not None and (
        provider_override is not None or model_override is not None
    ):
        raise ValueError(
            "authenticated interactive dispatch route is fixed by its quote"
        )

    if idempotency_key is not None and (
        type(idempotency_key) is not str
        or not idempotency_key.strip()
        or len(idempotency_key) > 512
        or "\n" in idempotency_key
        or "\r" in idempotency_key
    ):
        raise ValueError("idempotency_key must be a bounded canonical string")
    if allowed_routes is not None and (
        not allowed_routes
        or any(
            type(route) is not str
            or not route.strip()
            or len(route) > 512
            or "/" not in route
            for route in allowed_routes
        )
    ):
        raise ValueError("allowed_routes must be a non-empty canonical route set")

    prompt_hash = _sha256_prefix(prompt)
    if interactive_authority is not None:
        try:
            tier, _, _ = _accepted_tier_chain(interactive_authority, role=role)
        except ResearchBudgetLedgerInvalid as exc:
            raise ProviderCallNotAttempted(
                f"interactive budget authority refused the route ({type(exc).__name__})",
                provider="<accepted-quote>",
                model="<accepted-quote>",
                latency_ms=0,
                retryable=False,
            ) from exc
        rows, _, _ = _accepted_research_routes(interactive_authority, role=role)
        tier_name = rows[0].logical_tier_name
        if max_tokens is not None and max_tokens != tier.max_tokens:
            raise ValueError(
                "authenticated interactive dispatch output limit is fixed by its quote"
            )
    else:
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
        tier = config.tiers[tier_name]
    # A route identity override cannot inherit another provider/model's price
    # authority. Keep execution limits and fallback shape, but make price
    # unknown so authenticated paid dispatch refuses until an exact route
    # resolver supplies a complete TierConfig.
    if interactive_authority is None and provider_override and model_override:
        tier = TierConfig(
            name=tier.name,
            provider=provider_override,
            model=model_override,
            max_tokens=tier.max_tokens,
            temperature=tier.temperature,
            context_budget_tokens=tier.context_budget_tokens,
            pricing=TierPricing(),
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
        # mypy --strict: bind the guard-narrowed fields once. TierConfig's
        # provider/model are Optional by design (placeholder tiers), and
        # attribute narrowing does not survive the calls below.
        provider_name: str = current.provider
        model_name: str = current.model
        route_key = f"{provider_name}/{model_name}"
        if allowed_routes is not None and route_key not in allowed_routes:
            # A signed route boundary is authority, not a fallback hint. Reject
            # before registry lookup, breaker inspection, or durable event I/O.
            raise ProviderCallNotAttempted(
                f"{provider_name}: route is outside the signed allowlist",
                provider=provider_name,
                model=model_name,
                latency_ms=0,
                retryable=False,
            )
        effective_max_tokens = (
            max_tokens if max_tokens is not None else current.max_tokens
        )
        budget_call: _InteractiveBudgetCall | None = None
        if interactive_authority is not None:
            try:
                budget_call = _prepare_interactive_budget_call(
                    authority=interactive_authority,
                    prompt=prompt,
                    prompt_hash=prompt_hash,
                    role=role,
                    tier_name=tier_name,
                    route=current,
                    fallback_chain_index=chain_index,
                    max_tokens=effective_max_tokens,
                    verification_required=verification_required,
                    context_pack_event_id=context_pack_event_id,
                    parent_event_id=parent_event_id,
                )
            except (
                IdempotencyConflict,
                ResearchBudgetExceeded,
                ResearchBudgetLedgerInvalid,
            ) as exc:
                raise ProviderCallNotAttempted(
                    f"{provider_name}: interactive budget authority refused the call "
                    f"({type(exc).__name__})",
                    provider=provider_name,
                    model=model_name,
                    latency_ms=0,
                    retryable=False,
                ) from exc
            if budget_call.terminal is not None:
                if isinstance(
                    budget_call.terminal.payload, ResearchCallReleasedPayload
                ):
                    current = current.fallback
                    chain_index += 1
                    continue
                if isinstance(
                    budget_call.terminal.payload, ResearchCallSettledPayload
                ):
                    # Re-enter with the same canonical provider idempotency key
                    # to reconstruct response text after a process crash. The
                    # dispatch and settlement receipts below are append-once.
                    pass
                else:
                    raise ValueError("research reservation terminal is not typed")
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
            if budget_call is not None:
                _release_interactive_budget_call(
                    budget_call, reason="provider_unregistered", error=e
                )
            else:
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
            if budget_call is not None:
                _release_interactive_budget_call(
                    budget_call, reason="circuit_open"
                )
            else:
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
                )
            current = current.fallback
            chain_index += 1
            continue

        t_start = time.monotonic()
        try:
            effective_idempotency_key = (
                budget_call.provider_idempotency_key
                if budget_call is not None
                else idempotency_key
            )
            if effective_idempotency_key is None:
                raw = provider.call(
                    model=model_name,
                    prompt=prompt,
                    max_tokens=effective_max_tokens,
                    temperature=(
                        budget_call.temperature
                        if budget_call is not None
                        else current.temperature
                    ),
                )
            elif isinstance(provider, IdempotentProvider):
                raw = provider.call_idempotent(
                    model=model_name,
                    prompt=prompt,
                    max_tokens=effective_max_tokens,
                    temperature=(
                        budget_call.temperature
                        if budget_call is not None
                        else current.temperature
                    ),
                    idempotency_key=effective_idempotency_key,
                )
            else:
                raise ProviderCallNotAttempted(
                    f"{provider_name}: idempotent dispatch is unavailable",
                    provider=provider_name,
                    model=model_name,
                    latency_ms=0,
                    retryable=False,
                )
        except ProviderError as e:
            if budget_call is not None and isinstance(e, ProviderCallNotAttempted):
                _release_interactive_budget_call(
                    budget_call,
                    reason="provider_call_not_attempted",
                    error=e,
                )
                last_error = e
                current = current.fallback
                chain_index += 1
                continue
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
            )
            # Count this genuine provider-call failure toward the breaker. Config
            # conditions (unregistered/no-key) never reach here — they fall
            # through at get_provider above — so every failure counted is real.
            if not isinstance(e, ProviderCallNotAttempted):
                default_breaker.record_failure(provider_name)
            last_error = e
            if effective_idempotency_key is not None and not isinstance(
                e, ProviderCallNotAttempted
            ):
                # A possibly attempted paid request may have reached this
                # provider. Cross-provider fallback would reuse a key outside
                # its dedupe domain and can double-bill. Stop immediately; the
                # caller retains the budget hold for reconciliation.
                raise
            current = current.fallback
            chain_index += 1
            continue

        # Success: normalize, cost, emit, return.
        default_breaker.record_success(provider_name)
        usage = provider.normalize_usage(raw.raw_usage)
        finish = normalize_finish_reason(raw.finish_reason)
        cost = _compute_cost_usd(
            usage,
            budget_call.pricing if budget_call is not None else current.pricing,
        )
        success_payload = DispatchCallPayload(
            provider=provider_name,
            model=model_name,
            tier=tier_name,  # type: ignore[arg-type]
            target_role=role,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
            latency_ms=raw.latency_ms,
            verification_required=verification_required,
            fallback_chain_index=chain_index,
            prompt_hash=prompt_hash,
            finish_reason=finish,
            context_pack_event_id=context_pack_event_id,
        )
        if budget_call is None:
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
            )
        else:
            dispatch_event = _success_dispatch_event_authorized(
                budget_call,
                success_payload,
                parent_event_id=parent_event_id,
            )
            settle_research_call_authorized(
                budget_call.authority,
                ResearchCallSettledPayload(
                    reservation_id=budget_call.reservation.reservation_id,
                    reservation_event_id=budget_call.reservation_event.event_id,
                    request_sha256=budget_call.reservation.request_sha256,
                    dispatch_call_event_id=dispatch_event.event_id,
                    actual_cost_usd=dispatch_event.payload.cost_usd,
                    exceeded_reservation=(
                        dispatch_event.payload.cost_usd
                        > budget_call.reservation.projected_max_cost_usd
                    ),
                ),
                role=role,
                policy_id=f"{provider_name}/{model_name}",
            )
            eid = dispatch_event.event_id
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
