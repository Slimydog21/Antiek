"""OpenAI TTS provider for interview voice mode (Sprint 17 mainline).

Per master-spec §11.5: WebRTC capture, whisper transcription
streaming, AI interviewer response via text-to-speech (ElevenLabs or
OpenAI TTS). Voice loop adds latency (~3-5s round-trip) but is the
right form factor for the operator's biography use case.

Sprint 17 ships substrate-side scaffolding; full WebRTC + streaming
wire-up is multi-day operator-driven work (real API keys + browser
audio context)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# A poster turns (url, headers, json_body) into the raw audio bytes the
# API returns. Injected so tests synthesize without a network call or a
# real key burn; production uses the httpx default below.
SpeechPoster = Callable[[str, dict, dict], bytes]


def _httpx_poster(url: str, headers: dict, json_body: dict) -> bytes:
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
    ) -> Any:
        """Synthesize speech. Returns a RawProviderResponse-shaped
        result with `text` as a base64-encoded audio blob.

        Substrate-internal: the dispatch event's input_tokens is the
        character count of the prompt; the cost computation in
        substrate.dispatch uses input_per_mtok pricing.

        This stub raises if no API key + no httpx test transport are
        configured. Full implementation lands when the operator wires
        the real OpenAI key into env + the WebRTC client connects."""
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY missing. Set the env var to enable TTS. "
                "Sprint 17 substrate scaffold; full wire-up requires "
                "operator API key + browser-side WebRTC capture."
            )
        # NOTE: real implementation would POST to /v1/audio/speech
        # with the appropriate model + voice + input_text. The current
        # scaffold raises rather than make a real call to avoid burning
        # operator credits autonomously.
        raise NotImplementedError(
            "Full TTS dispatch wire-up is operator-driven. Substrate-side "
            "tier config exists in substrate/dispatch/config.yaml (Sprint "
            "17 addition); browser-side WebRTC capture in acquisition/voice/"
            "; the wire-up between them is multi-day engineering."
        )

    def synthesize(
        self,
        text: str,
        *,
        model: str | None = None,
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
        if poster is None and not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY missing. Set the env var to enable TTS voice replies."
            )
        # Lineup binding (voice action): the operator's lineup assignment
        # for `text_to_speech` wins over the gpt-4o-mini-tts default when it
        # names an admissible model; an explicit caller model always wins.
        from substrate.dispatch.lineup_override import effective_model_for_action
        model = model or effective_model_for_action(
            "text_to_speech", provider_family="openai", default="gpt-4o-mini-tts",
        )
        post = poster or _httpx_poster
        return post(
            f"{self.base_url}/audio/speech",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            {"model": model, "voice": voice or self.voice, "input": text, "response_format": "mp3"},
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> dict[str, int]:
        """TTS has no token usage in the traditional sense. Returns
        zeros; the dispatch cost helper computes based on character
        count of the input prompt (per substrate.dispatch tier config)."""
        return {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
