"""Canonical in-memory audio request bytes; no credential, funds or send authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Literal

from acquisition.voice.audio_bound import MAX_INPUT_BYTES, NormalizedAudio
from acquisition.voice.audio_cost import (
    AudioCostError,
    AudioCostQuote,
    QualifiedAudioTariff,
    quote_audio_cost,
)
from runtime.research_runner.audio_provider_catalog import AudioModelDescriptor

MAX_FRAMING_BYTES = 4096
MAX_REQUEST_BYTES = MAX_INPUT_BYTES + MAX_FRAMING_BYTES


class AudioRequestError(ValueError):
    """Value-free refusal before any transport or payment effect."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PreparedAudioRequest:
    body: bytes = field(repr=False)
    body_sha256: str
    content_type: str
    boundary: str
    byte_count: int
    method: Literal["POST"]
    endpoint: Literal["https://api.openai.com"]
    request_path: Literal["/v1/audio/transcriptions"]
    language: str | None
    quote: AudioCostQuote


def _validate_capability(capability: AudioModelDescriptor) -> None:
    if type(capability) is not AudioModelDescriptor:
        raise AudioRequestError("unsupported_audio_capability")
    expected = {
        "catalog_id": "openai",
        "model_id": "whisper-1",
        "adapter_kind": "audio_transcription",
        "operation": "transcribe",
        "endpoint": "https://api.openai.com",
        "request_path": "/v1/audio/transcriptions",
    }
    for name, value in expected.items():
        actual: object = getattr(capability, name, None)
        if type(actual) is not str or actual != value:
            raise AudioRequestError("unsupported_audio_capability")


def _validate_language(language: str | None) -> None:
    if language is not None and (
        type(language) is not str or re.fullmatch(r"[a-z]{2}", language) is None
    ):
        raise AudioRequestError("invalid_audio_language")


def _boundary(quote: AudioCostQuote, language: str | None) -> str:
    binding = {
        "version": 1,
        "audio_binding_sha256": quote.audio_binding_sha256,
        "capability_sha256": quote.capability_sha256,
        "language": language,
    }
    digest = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return "asr1-" + digest


def prepare_audio_request(
    audio: NormalizedAudio,
    capability: AudioModelDescriptor,
    policy: QualifiedAudioTariff | None,
    *,
    now: datetime,
    language: str | None = None,
) -> PreparedAudioRequest:
    """Prepare one deterministic multipart body from authoritative server inputs.

    The returned quote is an estimate. The caller still needs independent
    owner, budget, operation, credential and one-use-send admission.
    """
    _validate_capability(capability)
    _validate_language(language)
    try:
        quote = quote_audio_cost(audio, capability, policy, now=now)
    except AudioCostError as error:
        raise AudioRequestError(error.code) from None
    except (AttributeError, TypeError, ValueError) as _error:
        raise AudioRequestError("invalid_authoritative_audio_inputs") from None
    boundary = _boundary(quote, language)
    delimiter = b"--" + boundary.encode("ascii")
    if delimiter in audio.wav:
        raise AudioRequestError("audio_framing_collision")
    values = [("model", "whisper-1"), ("response_format", "verbose_json")]
    if language is not None:
        values.append(("language", language))
    prefixes = [
        delimiter
        + b'\r\nContent-Disposition: form-data; name="'
        + name.encode("ascii")
        + b'"\r\n\r\n'
        + value.encode("ascii")
        + b"\r\n"
        for name, value in values
    ]
    file_prefix = (
        delimiter
        + b'\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"'
        + b"\r\nContent-Type: audio/wav\r\n\r\n"
    )
    closing = b"\r\n" + delimiter + b"--\r\n"
    framing_size = sum(len(prefix) for prefix in prefixes) + len(file_prefix) + len(closing)
    expected_size = len(audio.wav) + framing_size
    if framing_size > MAX_FRAMING_BYTES or expected_size > MAX_REQUEST_BYTES:
        raise AudioRequestError("audio_request_too_large")
    body = b"".join((*prefixes, file_prefix, audio.wav, closing))
    return PreparedAudioRequest(
        body=body,
        body_sha256=hashlib.sha256(body).hexdigest(),
        content_type="multipart/form-data; boundary=" + boundary,
        boundary=boundary,
        byte_count=expected_size,
        method="POST",
        endpoint="https://api.openai.com",
        request_path="/v1/audio/transcriptions",
        language=language,
        quote=quote,
    )


def _same_binding(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, (AudioCostQuote, AudioModelDescriptor)):
        return all(
            _same_binding(getattr(actual, item.name), getattr(expected, item.name))
            for item in fields(expected)
        )
    return bool(actual == expected)


def validate_audio_request(
    prepared: PreparedAudioRequest,
    audio: NormalizedAudio,
    capability: AudioModelDescriptor,
    policy: QualifiedAudioTariff | None,
    *,
    now: datetime,
    language: str | None = None,
) -> None:
    """Reconstruct from current authoritative inputs and reject any alteration.

    Equality of this value never grants credentials, payment or send authority.
    """
    if type(prepared) is not PreparedAudioRequest:
        raise AudioRequestError("invalid_prepared_audio_request")
    expected = prepare_audio_request(audio, capability, policy, now=now, language=language)
    try:
        valid = all(
            _same_binding(getattr(prepared, item.name), getattr(expected, item.name))
            for item in fields(PreparedAudioRequest)
        )
    except (AttributeError, TypeError, ValueError) as _error:
        valid = False
    if not valid:
        raise AudioRequestError("audio_request_binding_mismatch")
