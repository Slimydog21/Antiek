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
from dataclasses import dataclass
from typing import Any, Optional


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
    api_key: Optional[str] = None
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

    def normalize_usage(self, raw_usage: dict[str, Any]) -> dict[str, int]:
        """TTS has no token usage in the traditional sense. Returns
        zeros; the dispatch cost helper computes based on character
        count of the input prompt (per substrate.dispatch tier config)."""
        return {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
