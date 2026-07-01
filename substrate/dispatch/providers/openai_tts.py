"""OpenAI TTS provider for interview voice mode (Sprint 17 mainline).

Per master-spec §11.5: WebRTC capture, whisper transcription
streaming, AI interviewer response via text-to-speech (ElevenLabs or
OpenAI TTS). Voice loop adds latency (~3-5s round-trip) but is the
right form factor for the operator's biography use case.

Sprint 17 ships substrate-side scaffolding; full WebRTC + streaming
wire-up is multi-day operator-driven work (real API keys + browser
audio context)."""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from substrate.dispatch.base import NormalizedUsage, ProviderError, RawProviderResponse

# A poster turns (url, headers, json_body) into the raw audio bytes the
# API returns. Injected so tests synthesize without a network call or a
# real key burn; production uses the httpx default below.
SpeechPoster = Callable[[str, dict[str, str], dict[str, str]], bytes]


def _httpx_poster(url: str, headers: dict[str, str], json_body: dict[str, str]) -> bytes:
    import httpx

    resp = httpx.post(url, headers=headers, json=json_body, timeout=60.0)
    resp.raise_for_status()
    return resp.content


@dataclass
class OpenAITTSProvider:
    """Calls OpenAI's /v1/audio/speech endpoint. Returns mp3 bytes.

    Per master-spec dispatch config (Sprint 17 addition):
        tts:
          provider: openai
          model: gpt-4o-mini-tts
          pricing: input_per_mtok 15.0  # per million characters

    The substrate accounts characters as input tokens; output is
    audio bytes, not tokens, so output_per_mtok = 0.
    """

    name: str = "openai"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    voice: str = "alloy"  # OpenAI's six pre-defined voices; operator can override
    poster: SpeechPoster | None = None

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("OPENAI_API_KEY")

    def call(
        self,
        *,
        model: str,
        prompt: str,  # the text to speak
        max_tokens: int,  # unused for TTS
        temperature: float,  # unused for TTS
    ) -> RawProviderResponse:
        """Synthesize speech. Returns a RawProviderResponse-shaped
        result with `text` as a base64-encoded audio blob.

        Substrate-internal: the dispatch event's input_tokens is the
        character count of the prompt; the cost computation in
        substrate.dispatch uses input_per_mtok pricing.

        The returned ``text`` is base64-encoded mp3 bytes so the synchronous
        dispatch router can carry it without inventing a binary response path.
        """
        started = time.monotonic()
        if not self.api_key:
            raise ProviderError(
                "OPENAI_API_KEY missing. Set the env var to enable TTS. "
                "The TTS adapter never burns credits without an operator key.",
                provider=self.name,
                model=model,
                latency_ms=0,
                retryable=False,
            )
        try:
            audio = self.synthesize(prompt, model=model)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI TTS call failed: {exc}",
                provider=self.name,
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                retryable=True,
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        return RawProviderResponse(
            text=base64.b64encode(audio).decode("ascii"),
            raw_usage={
                "input_characters": len(prompt),
                "input_tokens": len(prompt),
                "output_tokens": 0,
                "audio_bytes": len(audio),
            },
            finish_reason="stop",
            latency_ms=latency_ms,
            extra={"mime_type": "audio/mpeg", "encoding": "base64"},
        )

    def synthesize(
        self,
        text: str,
        *,
        model: str = "gpt-4o-mini-tts",
        voice: str | None = None,
        poster: SpeechPoster | None = None,
    ) -> bytes:
        """Synthesize ``text`` to mp3 bytes via OpenAI's /v1/audio/speech.

        This is the async-reply path (Read SPR-07 voice replies): the AI's
        text answer is spoken on demand. It is NOT the gated real-time
        talk-to-book loop — that stays gated on speech round-trip latency
        (~3–5s today; the operator's own "if models get good enough" bar).

        Gated on the API key exactly as the dispatch scaffold was: no key
        ⇒ RuntimeError, so this never burns credits without an operator
        key present. ``poster`` is injectable; tests pass a stub so no
        network call (and no key) is needed.
        """
        if not text.strip():
            raise ValueError("cannot synthesize empty text")
        if poster is None and self.poster is None and not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY missing. Set the env var to enable TTS voice replies."
            )
        post = poster or self.poster or _httpx_poster
        return post(
            f"{self.base_url}/audio/speech",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            {"model": model, "voice": voice or self.voice, "input": text, "response_format": "mp3"},
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        """Normalize TTS usage into the router's token-shaped accounting.

        The TTS tier prices input text per million characters. The dispatch
        router's cost math is token-shaped, so the adapter reports one
        "input token" per input character for this provider only.
        """
        return NormalizedUsage(
            input_tokens=int(
                raw_usage.get("input_characters", raw_usage.get("input_tokens", 0)) or 0
            ),
            output_tokens=int(raw_usage.get("output_tokens", 0) or 0),
            cached_input_tokens=0,
            cache_creation_input_tokens=0,
        )
