"""Anthropic Provider adapter.

Response shape this adapter parses (Anthropic Messages API):

```
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "model": "...",
  "content": [{"type": "text", "text": "..."}],
  "stop_reason": "end_turn" | "max_tokens" | "stop_sequence" | "tool_use",
  "stop_sequence": null,
  "usage": {
    "input_tokens": N,                  // tokens AFTER the last cache breakpoint — cache-EXCLUSIVE
    "output_tokens": M,
    "cache_creation_input_tokens": N,   // tokens WRITTEN to cache this call (premium 1.25x write rate)
    "cache_read_input_tokens": N        // tokens READ from cache this call (discounted 0.1x read rate)
  }
}
```

Usage normalization (the cost-accounting watch-item): per the Anthropic
Messages API prompt-caching schema, ``input_tokens`` is the number of
input tokens "which were not read from or used to create a cache (that
is, tokens after the last cache breakpoint)" — it is the cache-EXCLUSIVE
remainder, NOT an inclusive total. ``cache_read_input_tokens`` and
``cache_creation_input_tokens`` are reported SEPARATELY and are NOT
contained in ``input_tokens``. The true total input is therefore
``cache_read_input_tokens + cache_creation_input_tokens + input_tokens``.

``NormalizedUsage`` expects an INCLUSIVE ``input_tokens`` (the router's
single cost function subtracts the cached/written subsets uniformly across
providers). So ``normalize_usage`` below sums the three Anthropic fields
into an inclusive total and forwards the cached-read and cache-write
subsets separately, letting ``_compute_cost_usd`` bill cache_read at the
discounted rate and cache_creation at the premium write rate.

NOTE: the earlier comment here claimed ``input_tokens`` "already includes
cached tokens" — that was FALSE for the real Anthropic API and caused the
router's ``paid_input = max(0, input - cached)`` to double-subtract and
clamp to zero on a cache hit (underbilling, and silently dropping the
premium cache_creation writes). OpenAI/DeepSeek ``prompt_tokens`` genuinely
IS inclusive, so the false symmetry assumption held there but not here.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

try:
    from ..base import (
        NormalizedUsage,
        ProviderError,
        RawProviderResponse,
    )
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from dispatch.base import (  # type: ignore[no-redef]
        NormalizedUsage,
        ProviderError,
        RawProviderResponse,
    )


_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})
_DEFAULT_TIMEOUT_S = 120.0

# Anthropic API version header. Update when adopting a newer API version.
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    """Provider implementation for Anthropic's Messages API.

    Construct one shared instance and register with the router:

        anthropic = AnthropicProvider(api_key_env="ANTHROPIC_API_KEY")
        register_provider(anthropic)

    The router looks the instance up by ``name`` (``"anthropic"``,
    matching ``config.yaml``).
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
        anthropic_version: str = _ANTHROPIC_VERSION,
        enable_prompt_caching: bool = False,
        expose_error_body: bool = True,
    ):
        """
        Args:
            api_key: Explicit key for tests; production uses ``api_key_env``.
            api_key_env: Environment variable holding the API key.
            base_url: Anthropic API root.
            timeout_s: Per-call timeout.
            client: Injectable httpx.Client (tests use MockTransport).
            anthropic_version: ``anthropic-version`` header value.
            enable_prompt_caching: If True, sends ``cache_control`` on the
                user message so subsequent calls with the same prefix can
                read from cache. Off by default — turn on once the
                dispatch caller starts re-using stable system prompts.
            expose_error_body: Include a bounded upstream response-body preview
                in provider errors. User-configured endpoints disable this so
                a hostile endpoint cannot reflect a request credential into an
                exception that may later be returned, logged, or persisted.
        """
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None
        self._anthropic_version = anthropic_version
        self._enable_prompt_caching = enable_prompt_caching
        self._expose_error_body = expose_error_body

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        v = os.environ.get(self._api_key_env)
        if not v:
            raise ProviderError(
                f"anthropic: API key not configured. Set {self._api_key_env} "
                "in the environment or pass api_key= to the adapter.",
                provider=self.name, model="<unknown>", latency_ms=0,
            )
        return v

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def call(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> RawProviderResponse:
        api_key = self._resolve_api_key()
        url = self.base_url + "/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self._anthropic_version,
            "Content-Type": "application/json",
        }

        # Anthropic requires user-role messages with content as either a
        # string or a list of typed parts. Use the typed-parts form so we
        # can attach ``cache_control`` when caching is enabled.
        if self._enable_prompt_caching:
            messages = [{
                "role": "user",
                "content": [{
                    "type": "text", "text": prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
            }]
        else:
            messages = [{"role": "user", "content": prompt}]

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        client = self._ensure_client()
        t_start = time.monotonic()
        try:
            resp = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"anthropic: request timeout after {self._timeout_s}s — {e}",
                provider=self.name, model=model,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                retryable=True,
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(
                f"anthropic: network error — {e}",
                provider=self.name, model=model,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                retryable=True,
            ) from e
        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            detail = f" — {resp.text[:400]}" if self._expose_error_body else ""
            raise ProviderError(
                f"anthropic: HTTP {resp.status_code}{detail}",
                provider=self.name, model=model,
                latency_ms=latency_ms,
                retryable=resp.status_code in _RETRYABLE_STATUS,
                request_id=resp.headers.get("request-id") or resp.headers.get("x-request-id"),
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError(
                f"anthropic: response body not JSON — {e}",
                provider=self.name, model=model, latency_ms=latency_ms,
            ) from e

        try:
            # Anthropic returns content as a list of typed parts. Join the
            # text parts; ignore non-text parts (tool_use etc. handled in
            # a later signature when dispatch supports tools).
            parts = data.get("content") or []
            text = "".join(
                p["text"] for p in parts
                if isinstance(p, dict) and p.get("type") == "text" and "text" in p
            )
            stop_reason = data.get("stop_reason")
        except (KeyError, TypeError) as e:
            detail = (
                f" — body: {str(data)[:400]}" if self._expose_error_body else ""
            )
            raise ProviderError(
                f"anthropic: unexpected response shape — {e}{detail}",
                provider=self.name, model=model, latency_ms=latency_ms,
            ) from e

        return RawProviderResponse(
            text=text,
            raw_usage=data.get("usage") or {},
            finish_reason=stop_reason,
            latency_ms=latency_ms,
            request_id=resp.headers.get("request-id") or data.get("id"),
            extra={"model": data.get("model")},
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        if not raw_usage:
            return NormalizedUsage(input_tokens=0, output_tokens=0)
        # Anthropic's ``input_tokens`` is the cache-EXCLUSIVE remainder
        # ("tokens after the last cache breakpoint" — Anthropic Messages
        # API prompt-caching schema). ``cache_read_input_tokens`` and
        # ``cache_creation_input_tokens`` are reported SEPARATELY and are
        # NOT inside ``input_tokens``. ``NormalizedUsage`` expects an
        # INCLUSIVE total, so we sum all three to present the router an
        # inclusive ``input_tokens`` and forward the read/write subsets so
        # ``_compute_cost_usd`` can bill cache_read at the discounted rate
        # and cache_creation at the premium (1.25x base input) write rate.
        # WHY this changed: the previous adapter forwarded the
        # cache-exclusive remainder verbatim, so the router's
        # ``max(0, input - cached)`` double-subtracted and clamped to zero
        # on a normal cache hit — underbilling and dropping the premium
        # cache_creation writes entirely.
        input_remainder = int(raw_usage.get("input_tokens", 0) or 0)
        cache_read = int(raw_usage.get("cache_read_input_tokens", 0) or 0)
        cache_creation = int(raw_usage.get("cache_creation_input_tokens", 0) or 0)
        return NormalizedUsage(
            input_tokens=input_remainder + cache_read + cache_creation,
            output_tokens=int(raw_usage.get("output_tokens", 0) or 0),
            cached_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None
