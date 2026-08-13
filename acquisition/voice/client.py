"""Voice acquisition client — whisper transcription.

OpenAI's whisper-1 endpoint is the only sanctioned path at Sprint 13.
The ``Transcriber`` protocol is injected so tests can supply a stub
(``StubTranscriber``) and so a future local whisper.cpp path can drop
in without touching adapter call sites.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

DEFAULT_TIMEOUT_S = 120.0  # whisper can take ~60s on a 20-min clip
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_WHISPER_MODEL = "whisper-1"


@dataclass(frozen=True)
class Transcript:
    """Whisper response, normalized."""

    text: str
    language: str | None
    duration_seconds: float  # 0.0 if not advertised
    model: str


class Transcriber(Protocol):
    """Injectable transcription interface."""

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript:
        ...


class WhisperTranscriber:
    """OpenAI whisper-1 transcriber. Default path in production."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = (base_url or os.environ.get(
            "ANTIEK_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL,
        )).rstrip("/")
        # Lineup binding (voice action): the operator's lineup assignment
        # for `transcription` wins over the whisper-1 default when it names
        # an admissible model; an explicit caller model always wins.
        from substrate.dispatch.lineup_override import effective_model_for_action
        self._model = model or effective_model_for_action(
            "transcription", provider_family="openai", default=DEFAULT_WHISPER_MODEL,
        )
        self._client = client

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        language: str | None = None,
    ) -> Transcript:
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set; cannot call whisper. Set the env "
                "var or inject a stub Transcriber for tests."
            )
        files = {"file": (filename, audio_bytes, "audio/mpeg")}
        data = {"model": self._model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/audio/transcriptions"
        # ``base_url`` is env/param-overridable, so route the send through the
        # host-based gate. The default api.openai.com host is posted directly;
        # were the base ever an arXiv host it would be governed.
        from acquisition.arxiv.rate_governor import (
            canonical_arxiv_throttle,
            govern_if_arxiv,
        )

        if self._client is not None:
            def _send() -> httpx.Response:
                return self._client.post(
                    url, headers=headers, files=files, data=data,
                    timeout=DEFAULT_TIMEOUT_S,
                )

            r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
        else:
            with httpx.Client(timeout=DEFAULT_TIMEOUT_S) as c:
                def _send() -> httpx.Response:
                    return c.post(
                        url, headers=headers, files=files, data=data,
                        timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
                    )

                r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
        r.raise_for_status()
        body = r.json()
        return Transcript(
            text=str(body.get("text", "")).strip(),
            language=body.get("language"),
            duration_seconds=float(body.get("duration") or 0.0),
            model=self._model,
        )


def transcribe_audio(
    audio_bytes: bytes,
    *,
    filename: str,
    language: str | None = None,
    transcriber: Transcriber | None = None,
) -> Transcript:
    """Module-level convenience. In production the default
    ``WhisperTranscriber`` reads ``OPENAI_API_KEY`` from the env;
    tests pass a stub via ``transcriber=``."""
    t = transcriber or WhisperTranscriber()
    return t.transcribe(audio_bytes, filename=filename, language=language)
