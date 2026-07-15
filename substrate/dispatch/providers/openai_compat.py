"""OpenAI-compatible Provider adapter.

One adapter covers every API that speaks the OpenAI chat-completions
shape — DeepSeek, Xiaomi MiMo, Prime, OpenAI itself, OpenRouter. Each
becomes an instance with its own ``base_url`` and credentials.

Response shape this adapter parses (OpenAI Chat Completions):

```
{
  "id": "...",
  "object": "chat.completion",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop" | "length" | "content_filter" | "tool_calls" | "function_call"
  }],
  "usage": {
    "prompt_tokens": N,
    "completion_tokens": M,
    "total_tokens": N+M,
    "prompt_tokens_details": {"cached_tokens": C}   // optional, varies by provider
  }
}
```

The cache field is the watch-item: DeepSeek puts it at
``usage.prompt_cache_hit_tokens`` historically, OpenAI puts it at
``usage.prompt_tokens_details.cached_tokens``. The adapter reads both
and prefers the OpenAI shape (the dominant one in 2026). Add other
shapes to ``_extract_cached_tokens`` as new providers surface them.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

# Package-relative imports with direct-script fallback.
try:
    from ..base import (
        NormalizedUsage,
        ProviderError,
        RawProviderResponse,
        response_contains_secret,
    )
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from dispatch.base import (  # type: ignore[no-redef]
        NormalizedUsage,
        ProviderError,
        RawProviderResponse,
        response_contains_secret,
    )


# HTTP status → retryability. 429 (rate limit) and 5xx are retryable;
# 4xx other than 429 are configuration / quota / malformed-request
# errors and should not retry.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Default request timeout (seconds). Long enough for a slow synthesis
# call; short enough that a hung connection doesn't deadlock the
# dispatch loop. Override via constructor.
_DEFAULT_TIMEOUT_S = 120.0


def _extract_cached_tokens(usage: dict[str, Any]) -> int:
    """Read the cached-input-token count from the provider's usage shape.

    Watch-item: providers diverge on this field name. Add new shapes
    here when they appear; never let the router compute cost without
    knowing how many tokens were cached.
    """
    # OpenAI shape (dominant, also adopted by DeepSeek v3+ and MiMo)
    details = usage.get("prompt_tokens_details") or {}
    if "cached_tokens" in details:
        return int(details["cached_tokens"] or 0)
    # DeepSeek legacy / explicit field
    if "prompt_cache_hit_tokens" in usage:
        return int(usage["prompt_cache_hit_tokens"] or 0)
    return 0


class OpenAICompatProvider:
    """Provider implementation for OpenAI-shaped chat-completions APIs.

    Construct one instance per provider endpoint:

        deepseek = OpenAICompatProvider(
            name="deepseek",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        )
        register_provider(deepseek)

    The router looks the instance up by ``name`` (must match
    ``config.yaml``'s ``tiers[*].provider`` field).
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str = "OPENAI_API_KEY",
        api_key: str | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
        chat_completions_path: str = "/v1/chat/completions",
        extra_body: dict[str, Any] | None = None,
        expose_error_body: bool = True,
    ):
        """
        Args:
            name: Identifier used by the router and ``config.yaml``.
            base_url: Provider base URL (e.g. ``https://api.deepseek.com``).
                The chat-completions path is appended; pass it via
                ``chat_completions_path`` if the provider deviates.
            api_key_env: Environment variable holding the API key.
                Ignored if ``api_key`` is passed directly.
            api_key: Explicit key. Test fixtures use this; production
                code should rely on the env var.
            timeout_s: Request timeout. Per-call.
            client: Override the underlying httpx client. Used by tests
                with ``httpx.MockTransport`` to avoid network I/O.
            chat_completions_path: Path appended to ``base_url``. Some
                providers omit the ``/v1`` prefix; configure here.
            extra_body: Extra fields merged into every request body
                (e.g. ``{"thinking": {"type": "disabled"}}`` for z.ai's
                GLM-5.2 reasoning-toggle). Lets a vendor-specific provider
                pass non-standard params without a subclass. Defaults to
                none (standard OpenAI body only).
            expose_error_body: Include a bounded upstream response-body preview
                in provider errors. Disable this for user-configured endpoints:
                an untrusted endpoint can reflect request credentials in its
                response, and ProviderError messages may cross API or logging
                boundaries.
        """
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.chat_completions_path = chat_completions_path
        self._api_key = api_key
        self._api_key_env = api_key_env
        self._timeout_s = timeout_s
        # Inject for tests; otherwise build on first call.
        self._client = client
        self._owns_client = client is None
        self._extra_body = dict(extra_body) if extra_body else {}
        self._expose_error_body = expose_error_body

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        v = os.environ.get(self._api_key_env)
        if not v:
            raise ProviderError(
                f"{self.name}: API key not configured. Set {self._api_key_env} "
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
        url = self.base_url + self.chat_completions_path
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Vendor-specific fields (e.g. z.ai's reasoning toggle) merge on
        # top, never overriding the core request shape.
        if self._extra_body:
            body.update(self._extra_body)

        client = self._ensure_client()
        t_start = time.monotonic()
        resp: httpx.Response | None = None
        sanitized_transport_error: str | None = None
        try:
            resp = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            if self._expose_error_body:
                raise ProviderError(
                    f"{self.name}: request timeout after {self._timeout_s}s — {e}",
                    provider=self.name, model=model,
                    latency_ms=int((time.monotonic() - t_start) * 1000),
                    retryable=True,
                ) from e
            sanitized_transport_error = (
                f"{self.name}: request timeout after {self._timeout_s}s"
            )
        except httpx.RequestError as e:
            if self._expose_error_body:
                raise ProviderError(
                    f"{self.name}: network error — {e}",
                    provider=self.name, model=model,
                    latency_ms=int((time.monotonic() - t_start) * 1000),
                    retryable=True,
                ) from e
            sanitized_transport_error = f"{self.name}: network error"

        # Raise only after leaving the ``except`` context. ``raise ... from
        # None`` would hide the cause in formatted tracebacks but still retain
        # it in ``__context__``, including httpx's credential-bearing request.
        if sanitized_transport_error is not None:
            raise ProviderError(
                sanitized_transport_error,
                provider=self.name, model=model,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                retryable=True,
            )
        assert resp is not None
        latency_ms = int((time.monotonic() - t_start) * 1000)

        if resp.status_code != 200:
            detail = f" — {resp.text[:400]}" if self._expose_error_body else ""
            raise ProviderError(
                f"{self.name}: HTTP {resp.status_code}{detail}",
                provider=self.name, model=model,
                latency_ms=latency_ms,
                retryable=resp.status_code in _RETRYABLE_STATUS,
                request_id=(
                    resp.headers.get("x-request-id")
                    if self._expose_error_body
                    else None
                ),
            )

        # User-configured endpoints are untrusted. They already receive the
        # credential to authenticate the call, but must not be able to reflect
        # it into a nominally successful model response that Antiek would then
        # return, log, or persist as generated content.
        if not self._expose_error_body and api_key in resp.text:
            raise ProviderError(
                f"{self.name}: upstream response contained credential material; "
                "response rejected.",
                provider=self.name, model=model, latency_ms=latency_ms,
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderError(
                f"{self.name}: response body not JSON — {e}",
                provider=self.name, model=model, latency_ms=latency_ms,
            ) from e

        if (
            not self._expose_error_body
            and response_contains_secret(data, api_key)
        ):
            raise ProviderError(
                f"{self.name}: upstream response contained credential material; "
                "response rejected.",
                provider=self.name, model=model, latency_ms=latency_ms,
            )

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as e:
            detail = (
                f" — body: {str(data)[:400]}" if self._expose_error_body else ""
            )
            raise ProviderError(
                f"{self.name}: unexpected response shape — {e}{detail}",
                provider=self.name, model=model, latency_ms=latency_ms,
            ) from e

        if not self._expose_error_body and api_key in text:
            raise ProviderError(
                f"{self.name}: upstream response contained credential material; "
                "response rejected.",
                provider=self.name, model=model, latency_ms=latency_ms,
            )

        return RawProviderResponse(
            text=text,
            raw_usage=data.get("usage") or {},
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            request_id=(
                (resp.headers.get("x-request-id") or data.get("id"))
                if self._expose_error_body
                else None
            ),
            extra={"object": data.get("object")} if self._expose_error_body else {},
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        if not raw_usage:
            return NormalizedUsage(input_tokens=0, output_tokens=0)
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
            cached_input_tokens=_extract_cached_tokens(raw_usage),
        )

    def close(self) -> None:
        """Close the underlying httpx client if we own it."""
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None
