"""OpenAI GPT-4V vision provider adapter (Sprint 30+ thread 4).

Sibling to ``vision_anthropic.py``. Implements the same
``VisionProvider`` protocol so the operator can swap providers
without touching the visual bridge handler.

Uses OpenAI's Chat Completions API with the ``image_url`` content
block (multimodal messages). Compatible with gpt-4o,
gpt-4o-mini, and the GPT-4-vision-preview family.
"""

from __future__ import annotations

import os
import time

import httpx

from ._safe_diagnostics import correlation_digest
from .vision_anthropic import (
    VisionDispatchResult,
    VisionProviderError,
)

_DEFAULT_TIMEOUT_S = 120.0


class OpenAIVisionProvider:
    """OpenAI Chat Completions API adapter for vision-capable models.

    Sends ``messages`` with multimodal content: an image_url block +
    a text block. The system prompt rides as a separate system-role
    message (standard OpenAI shape — unlike Anthropic which carries
    ``system`` as a top-level field).
    """

    name = "openai_vision"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.openai.com",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        v = os.environ.get(self._api_key_env)
        if not v:
            raise VisionProviderError(
                f"openai_vision: API key not configured. "
                f"Set {self._api_key_env} in the environment or pass "
                "api_key= to the adapter."
            )
        return v

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def call_vision(
        self,
        *,
        system_prompt: str,
        user_text: str,
        image_url: str,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> VisionDispatchResult:
        """Dispatch one vision call. Raises ``VisionProviderError`` on
        any HTTP / parse failure."""
        client = self._ensure_client()
        body = {
            "model": model,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._resolve_api_key()}",
            "content-type": "application/json",
        }
        t_start = time.monotonic()
        try:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise VisionProviderError(
                f"openai_vision: HTTP transport failure ({type(exc).__name__})",
                provider=self.name,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                retryable=True,
            ) from None

        latency_ms = int((time.monotonic() - t_start) * 1000)
        if response.status_code != 200:
            raise VisionProviderError(
                f"openai_vision: HTTP {response.status_code} from "
                "OpenAI",
                provider=self.name,
                status_code=response.status_code,
                latency_ms=latency_ms,
                retryable=response.status_code in {429, 500, 502, 503, 504},
                request_id=correlation_digest(response.headers.get("x-request-id")),
            )

        try:
            data = response.json()
        except ValueError:
            raise VisionProviderError(
                "openai_vision: non-JSON response",
                provider=self.name,
                latency_ms=latency_ms,
            ) from None

        try:
            if not isinstance(data, dict):
                raise TypeError("expected response object")
            choices = data["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError("expected non-empty choices list")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError("expected choice object")
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError("expected message object")
            raw_text = message.get("content") or ""
            if not isinstance(raw_text, str):
                if not isinstance(raw_text, list):
                    raise TypeError("expected text or content parts")
                text_parts: list[str] = []
                for part in raw_text:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if isinstance(text, str):
                            text_parts.append(text)
                raw_text = "".join(text_parts)
            if not raw_text:
                raise TypeError("expected non-empty text content")
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                raise TypeError("expected usage object")
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
        except (KeyError, OverflowError, TypeError, ValueError):
            raise VisionProviderError(
                "openai_vision: unexpected response shape",
                provider=self.name,
                latency_ms=latency_ms,
            ) from None

        return VisionDispatchResult(
            raw_text=raw_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
        )


__all__ = [
    "OpenAIVisionProvider",
]
