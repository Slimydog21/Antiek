"""Voice acquisition client — whisper transcription.

OpenAI's whisper-1 endpoint is the only sanctioned path at Sprint 13.
The ``Transcriber`` protocol is injected so tests can supply a stub
(``StubTranscriber``) and so a future local whisper.cpp path can drop
in without touching adapter call sites.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

DEFAULT_TIMEOUT_S = 120.0  # whisper can take ~60s on a 20-min clip
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_WHISPER_MODEL = "whisper-1"


@dataclass(frozen=True)
class Transcript:
    """Whisper response, normalized."""

    text: str
    language: Optional[str]
    duration_seconds: float  # 0.0 if not advertised
    model: str


class Transcriber(Protocol):
    """Injectable transcription interface."""

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        language: Optional[str] = None,
    ) -> Transcript:
        ...


class WhisperTranscriber:
    """OpenAI whisper-1 transcriber. Default path in production."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = DEFAULT_WHISPER_MODEL,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = (base_url or os.environ.get(
            "ANTIEK_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL,
        )).rstrip("/")
        self._model = model
        self._client = client

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        language: Optional[str] = None,
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
        if self._client is not None:
            r = self._client.post(
                url, headers=headers, files=files, data=data,
                timeout=DEFAULT_TIMEOUT_S,
            )
        else:
            with httpx.Client(timeout=DEFAULT_TIMEOUT_S) as c:
                r = c.post(url, headers=headers, files=files, data=data)
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
    language: Optional[str] = None,
    transcriber: Optional[Transcriber] = None,
) -> Transcript:
    """Module-level convenience. In production the default
    ``WhisperTranscriber`` reads ``OPENAI_API_KEY`` from the env;
    tests pass a stub via ``transcriber=``."""
    t = transcriber or WhisperTranscriber()
    return t.transcribe(audio_bytes, filename=filename, language=language)
