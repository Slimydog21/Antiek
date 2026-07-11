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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

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
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.retryable = retryable
        self.request_id = request_id


class ProviderCallNotAttempted(ProviderError):
    """Failure proven to occur before any provider network request."""


# ---------------------------------------------------------------------------
# Normalized usage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedUsage:
    """Provider-agnostic usage breakdown. Adapters convert their own raw
    usage shape into this on every successful call.

    ``input_tokens`` is the INCLUSIVE total of input tokens billed for the
    call: it MUST already contain ``cached_input_tokens`` and
    ``cache_creation_input_tokens``. Some provider APIs report a
    cache-exclusive remainder (Anthropic's ``input_tokens`` is "tokens
    after the last cache breakpoint") while others report an inclusive
    total (OpenAI/DeepSeek ``prompt_tokens`` already includes cached
    tokens). Each adapter is responsible for converting its native shape
    into this inclusive convention so the router's single cost function
    can subtract the cached/written subsets uniformly.

    ``cached_input_tokens`` is the subset of ``input_tokens`` served from
    the provider's prompt cache at the discounted read rate (Anthropic
    ``cache_read_input_tokens``, OpenAI ``prompt_tokens_details.cached_tokens``),
    zero otherwise.

    ``cache_creation_input_tokens`` is the subset of ``input_tokens``
    written to the cache this call at the premium write rate (Anthropic
    ``cache_creation_input_tokens``), zero otherwise / when the provider
    does not expose a separate cache-write line.

    The router uses
    ``(input_tokens, cached_input_tokens, cache_creation_input_tokens, output_tokens)``
    together with the per-tier pricing entry to compute ``cost_usd``.
    Adapters MUST NOT compute cost themselves — keep pricing in one place.
    """

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


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
    finish_reason: str | None
    latency_ms: int
    request_id: str | None = None
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


@runtime_checkable
class IdempotentProvider(Protocol):
    """Optional paid-call contract used by restart-safe autonomous workers.

    Providers lacking this method are valid for interactive dispatch, but the
    router refuses to call them when an idempotency key is required.
    """

    name: str

    def call_idempotent(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        idempotency_key: str,
    ) -> RawProviderResponse: ...
