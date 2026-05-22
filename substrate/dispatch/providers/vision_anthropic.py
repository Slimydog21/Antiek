"""Anthropic Claude-Vision provider adapter (Sprint 30+ thread 4).

Vision provider for the substrate's 13th role (``roles/visual/``).
Builds Anthropic Messages API requests with an ``image`` content
block in addition to the role's text prompt.

Why this lives in a separate file from ``anthropic.py``: the
existing AnthropicProvider implements the dispatch ``call(prompt,
model, ...)`` protocol used by the twelve text-only roles. Vision
needs a different signature — the input is (system_prompt,
user_text, image_url) — so the visual bridge handler instantiates
a ``VisionProvider`` directly rather than going through the
router. Same HTTP plumbing, different interface contract.

Substrate stays VLM-agnostic at the role layer (``roles/visual/``
prompt + parser); this file is the Anthropic-specific binding.
Other providers (GPT-4V, Gemini-Pro-Vision) would land as siblings
that implement the same ``VisionProvider`` protocol.

Production wires:

    provider = AnthropicVisionProvider(api_key_env="ANTHROPIC_API_KEY")
    raw = provider.call_vision(
        system_prompt=VISUAL_SYSTEM_PROMPT,
        user_text=render_user_template(ctx),
        image_url="data:image/png;base64,...",
        model="claude-3-5-sonnet-20241022",
    )
    result = parse_visual_response(raw)

Tests inject ``MockVisionProvider`` (also in this module).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx


class VisionProviderError(Exception):
    """Surfaces structural / HTTP / auth failures from the provider.
    The visual bridge handler maps this to a
    ``VISUAL_ROLE_FAILED`` event with ``failure_kind="dispatch_error"``
    or ``"provider_unavailable"``."""


@dataclass(frozen=True)
class VisionDispatchResult:
    """The shape every VisionProvider returns.

    ``raw_text`` is the model's text response (will be parsed by
    ``parse_visual_response``). ``input_tokens`` / ``output_tokens``
    are the provider's usage metrics for billing aggregation.
    """

    raw_text: str
    input_tokens: int
    output_tokens: int
    model: str


class VisionProvider(Protocol):
    """The protocol any vision adapter satisfies. Production injects
    a concrete one (Anthropic / OpenAI / Gemini); tests inject a
    mock."""

    name: str

    def call_vision(
        self,
        *,
        system_prompt: str,
        user_text: str,
        image_url: str,
        model: str,
        max_output_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> VisionDispatchResult: ...


# ── Anthropic Claude-vision adapter ────────────────────────────────


_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_TIMEOUT_S = 120.0


class AnthropicVisionProvider:
    """Anthropic Messages API adapter with image support.

    Sends ``content`` as a list of two blocks: ``image`` (the frame)
    + ``text`` (the role's user-template). Per the Messages API
    contract, multi-block content is the way to combine images +
    text in one request.
    """

    name = "anthropic_vision"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: Optional[httpx.Client] = None,
        anthropic_version: str = _ANTHROPIC_VERSION,
    ):
        self._api_key = api_key
        self._api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None
        self._anthropic_version = anthropic_version

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        v = os.environ.get(self._api_key_env)
        if not v:
            raise VisionProviderError(
                f"anthropic_vision: API key not configured. "
                f"Set {self._api_key_env} in the environment or pass "
                "api_key= to the adapter."
            )
        return v

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def _build_image_block(self, image_url: str) -> dict:
        """Build the ``image`` content block. Supports two forms:

          - ``data:image/png;base64,XXXX`` — inline base64 (production
            for short-lived signed URLs)
          - ``https://...`` — Anthropic accepts ``source.type="url"``
            for hosted images (Beta as of writing; falls back to the
            substrate's responsibility to download + base64 if the
            provider variant doesn't support it)
        """
        if image_url.startswith("data:"):
            # parse "data:<media_type>;base64,<payload>"
            header, _, payload = image_url.partition(",")
            media_type = "image/png"
            if header.startswith("data:") and ";" in header:
                media_type = header[5:].split(";", 1)[0] or "image/png"
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": payload,
                },
            }
        return {
            "type": "image",
            "source": {"type": "url", "url": image_url},
        }

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
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        self._build_image_block(image_url),
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self._resolve_api_key(),
            "anthropic-version": self._anthropic_version,
            "content-type": "application/json",
        }
        try:
            response = client.post(
                f"{self.base_url}/v1/messages",
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise VisionProviderError(
                f"anthropic_vision: HTTP transport failure: {exc!r}",
            ) from exc

        if response.status_code != 200:
            raise VisionProviderError(
                f"anthropic_vision: HTTP {response.status_code} from "
                f"Anthropic Messages API: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise VisionProviderError(
                f"anthropic_vision: non-JSON response: {exc!r}",
            ) from exc

        # Extract text from the content blocks array.
        content = data.get("content") or []
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "")
                if isinstance(t, str):
                    text_parts.append(t)
        raw_text = "".join(text_parts)

        usage = data.get("usage") or {}
        return VisionDispatchResult(
            raw_text=raw_text,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            model=str(data.get("model", model)),
        )


# ── Test double ────────────────────────────────────────────────────


@dataclass
class MockVisionProvider:
    """Test injection. Returns a pre-canned ``VisionDispatchResult``;
    raises a pre-canned ``VisionProviderError`` if ``raise_with`` is
    set. Captures every call's args so tests can assert on what the
    role dispatch sent.

    Default name matches ``AnthropicVisionProvider`` so a swap is
    transparent to the bridge handler."""

    name: str = "anthropic_vision"
    canned_text: str = '{"frame_summary": "x.", "claims": []}'
    canned_input_tokens: int = 100
    canned_output_tokens: int = 50
    canned_model: str = "claude-3-5-sonnet-20241022"
    raise_with: Optional[VisionProviderError] = None
    calls: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

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
        self.calls.append({
            "system_prompt": system_prompt,
            "user_text": user_text,
            "image_url": image_url,
            "model": model,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        })
        if self.raise_with is not None:
            raise self.raise_with
        return VisionDispatchResult(
            raw_text=self.canned_text,
            input_tokens=self.canned_input_tokens,
            output_tokens=self.canned_output_tokens,
            model=self.canned_model,
        )


__all__ = [
    "AnthropicVisionProvider",
    "MockVisionProvider",
    "VisionDispatchResult",
    "VisionProvider",
    "VisionProviderError",
]
