"""Provider abstraction for the dispatch router.

Two concerns separated:

1. **The Provider protocol** — what every adapter must implement.
2. **Usage normalization** — the watch-item from week-1 planning.
   Anthropic returns ``{"input_tokens": N, "output_tokens": M}``;
   OpenAI-compatible APIs return ``{"prompt_tokens": N, "completion_tokens": M}``.
   Each adapter is responsible for normalizing its own raw usage into a
   ``NormalizedUsage`` instance. The router never inspects raw usage; if
   the normalization is wrong, every downstream cost report is wrong
   forever.

Adapters live in ``substrate/dispatch/providers/``. The router in
``router.py`` calls ``Provider.call(...)`` and ``Provider.normalize_usage(raw)``
and never reaches into provider-specific shapes.

Idempotency contract (DDIA-execution SPR-02, 2026-05-24)
========================================================

Every provider adapter MUST honor the following contract. The
verify-tier fallback in ``router.py`` depends on it; the cd602c9
chaos test (``tests/test_dispatch_fallback_chain.py``) exercises it.

I-DISPATCH-1 — Idempotency under retry
    A successful ``Provider.call(...)`` returning the same input
    (``model``, ``prompt``, ``max_tokens``, ``temperature``) MUST be
    safe to retry: either the provider returns a fresh response, or
    the adapter returns the cached one. Adapters MUST NOT raise on a
    duplicate request whose semantic effect is the same.
    Today: stateless API calls satisfy this trivially. When per-call
    side effects appear (tool-use callbacks, file uploads, etc.) the
    adapter MUST surface an idempotency key in the request and dedupe.

I-DISPATCH-2 — Failure mode taxonomy
    Adapters MUST classify failures into the three buckets of
    ``ProviderError.retryable``:
        retryable=True   → transient (network, 5xx, rate-limit). The
                           router may try the next tier in the chain
                           with the same prompt; downstream side effects
                           must NOT have occurred yet.
        retryable=False  → permanent (auth, model-not-found, content
                           policy). The router does NOT retry.
        ambiguous        → for in-flight failures whose effect is
                           unknown (e.g. socket-closed mid-stream). Map
                           to ``retryable=True`` only if the adapter can
                           prove no side effect; otherwise ``retryable=
                           False``. The router does not have enough
                           context to decide — the adapter does.

I-DISPATCH-3 — Verify-tier fallback ordering preserved
    ``router.py``'s fallback walks ``TierConfig.fallback`` chain in
    declaration order. Adapters MUST NOT reorder this. The chain order
    is the operator's bet (e.g. Hermes-primary for flash/pro/verify,
    OpenRouter-primary for synthesis during the 2-week measurement
    window per master-spec §14.4); silently reordering breaks the
    instrumentation that the dispatch verdict depends on.

I-DISPATCH-4 — OAuth-refresh → 503 translation rule
    The Hermes bridge (stewardship boundary: owned by Hermes Agent,
    NOT Antiek; see memory ``project_antiek_hermes_bridge.md``) raises
    HTTP 503 when its underlying provider's OAuth refresh fails. The
    Antiek-side Hermes adapter MUST map this to ``ProviderError(...,
    retryable=True)`` so the router falls through to the next chain
    member. Any other translation — silently retrying inside the
    adapter, raising a non-retryable error, or hiding the 503 — breaks
    the fallback chain's chaos-test contract at cd602c9. The Hermes
    adapter docstring restates this rule; both must stay in sync. If
    the rule changes, BOTH locations and ``docs/decisions/
    dispatch_idempotency_contract.md`` must change in the same PR.

I-DISPATCH-5 — Latency reported on failure
    ``ProviderError`` MUST be raised with ``latency_ms`` populated.
    Cost reports use this to attribute time-spent even when the call
    failed; without it, the dispatch verdict's tail-latency stats are
    biased toward the success path.

I-DISPATCH-6 — No cost computation in the adapter
    Adapters MUST NOT compute ``cost_usd``. Pricing lives in ONE
    place: ``router.py`` consumes ``NormalizedUsage`` plus
    ``TierConfig.pricing``. Adapters that pre-compute cost break the
    invariant; the boundary lint (DDIA-execution SPR-03) enforces
    this at the import level by blocking direct vendor imports
    outside ``substrate/dispatch/providers/``.

The chaos test for I-DISPATCH-3 + I-DISPATCH-4 is
``tests/test_dispatch_fallback_chain.py`` (commit cd602c9). DO NOT
modify that file as part of this contract work — it is the chaos-tested
verify-tier baseline. New tests for I-DISPATCH-1, I-DISPATCH-2,
I-DISPATCH-5, I-DISPATCH-6 go in
``tests/test_dispatch_idempotency_contract.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Raised by a provider adapter when a call fails. Includes the latency
    spent before failure so the router can record it in the failed
    DispatchCall event."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        latency_ms: int,
        retryable: bool = False,
        request_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.retryable = retryable
        self.request_id = request_id


# ---------------------------------------------------------------------------
# Normalized usage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedUsage:
    """Provider-agnostic usage breakdown. Adapters convert their own raw
    usage shape into this on every successful call.

    ``cached_input_tokens`` is a subset of ``input_tokens`` — the portion
    served from the provider's prompt cache. It is reported when the
    provider exposes it (Anthropic ``cache_read_input_tokens``, OpenAI
    ``prompt_tokens_details.cached_tokens``), zero otherwise.

    The router uses ``(input_tokens, cached_input_tokens, output_tokens)``
    together with the per-tier pricing entry to compute ``cost_usd``.
    Adapters MUST NOT compute cost themselves — keep pricing in one place.
    """

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


# ---------------------------------------------------------------------------
# Raw response wrapper
# ---------------------------------------------------------------------------


@dataclass
class RawProviderResponse:
    """What an adapter returns BEFORE normalization. The router calls
    ``provider.normalize_usage(raw.raw_usage)`` to get the typed
    ``NormalizedUsage``.

    ``finish_reason`` is normalized to the closed set documented on
    ``DispatchCallPayload`` (``stop`` / ``length`` / ``tool_use`` /
    ``content_filter`` / ``error``). Anthropic's ``end_turn`` and
    ``stop_sequence`` both map to ``stop``; ``max_tokens`` maps to
    ``length``. OpenAI's mapping is more direct.
    """

    text: str
    raw_usage: dict[str, Any]
    finish_reason: Optional[str]
    latency_ms: int
    request_id: Optional[str] = None
    # Additional provider-native metadata that the adapter wants to surface
    # for debugging but does not normalize. The router ignores this.
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Provider(Protocol):
    """Adapter contract. One instance per provider; the router holds a
    registry keyed by ``name``.

    ``name`` is the string used in ``config.yaml`` (e.g. ``"anthropic"``,
    ``"deepseek"``, ``"openai-compat"``, ``"hermes"``).
    """

    name: str

    def call(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> RawProviderResponse:
        """Synchronously call the provider. Raises ``ProviderError`` on
        provider-side failure; should NOT swallow exceptions.

        Adapters that wrap async clients should run the call in a
        ``run_until_complete``-style fashion; the router is synchronous by
        design (week 1 — async batched dispatch is a later concern).
        """
        ...

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        """Convert this provider's raw usage shape into ``NormalizedUsage``.

        Must handle the case where the provider returned partial or no
        usage data — return zeros rather than raising. The router emits
        the DispatchCall event regardless of whether usage was available.
        """
        ...
