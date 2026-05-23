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
from typing import Optional

import httpx

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
        api_key: Optional[str] = None,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.openai.com",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: Optional[httpx.Client] = None,
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
        try:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise VisionProviderError(
                f"openai_vision: HTTP transport failure: {exc!r}",
            ) from exc

        if response.status_code != 200:
            raise VisionProviderError(
                f"openai_vision: HTTP {response.status_code} from "
                f"OpenAI: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise VisionProviderError(
                f"openai_vision: non-JSON response: {exc!r}",
            ) from exc

        # Extract the assistant message text.
        choices = data.get("choices") or []
        if not choices:
            raise VisionProviderError(
                "openai_vision: response had no choices",
            )
        message = choices[0].get("message") or {}
        raw_text = message.get("content") or ""
        if not isinstance(raw_text, str):
            # gpt-4o sometimes returns content as a list of parts.
            text_parts: list[str] = []
            if isinstance(raw_text, list):
                for part in raw_text:
                    if isinstance(part, dict) and part.get("type") == "text":
                        t = part.get("text", "")
                        if isinstance(t, str):
                            text_parts.append(t)
            raw_text = "".join(text_parts)

        usage = data.get("usage") or {}
        return VisionDispatchResult(
            raw_text=raw_text,
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            model=str(data.get("model", model)),
        )


__all__ = [
    "OpenAIVisionProvider",
]
