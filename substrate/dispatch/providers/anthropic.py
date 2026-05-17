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
    "input_tokens": N,
    "output_tokens": M,
    "cache_creation_input_tokens": N,   // tokens that wrote to cache this call
    "cache_read_input_tokens": N        // tokens served FROM cache this call (subset of input_tokens)
  }
}
```

Watch-item: Anthropic's ``cache_read_input_tokens`` is the cached subset
of ``input_tokens``. We surface this on ``NormalizedUsage.cached_input_tokens``
so the router can apply the cached-input discount in
``_compute_cost_usd``. ``cache_creation_input_tokens`` is the first-write
cost and is folded into ``input_tokens`` already — do not double-count.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

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
        api_key: Optional[str] = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: Optional[httpx.Client] = None,
        anthropic_version: str = _ANTHROPIC_VERSION,
        enable_prompt_caching: bool = False,
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
        """
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None
        self._anthropic_version = anthropic_version
        self._enable_prompt_caching = enable_prompt_caching

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
            body_preview = resp.text[:400]
            raise ProviderError(
                f"anthropic: HTTP {resp.status_code} — {body_preview}",
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
            raise ProviderError(
                f"anthropic: unexpected response shape — {e} — body: {str(data)[:400]}",
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
        # ``input_tokens`` already includes cached tokens — Anthropic's
        # accounting treats cache_read as a discount, not a subtraction.
        # We pass the cached count separately so the router applies the
        # cached-input rate to that subset.
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0) or 0),
            output_tokens=int(raw_usage.get("output_tokens", 0) or 0),
            cached_input_tokens=int(raw_usage.get("cache_read_input_tokens", 0) or 0),
        )

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None
