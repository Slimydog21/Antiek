"""Independent multipart and refusal controls using synthetic canonical PCM only."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import replace
from datetime import UTC, datetime
from email import policy as mime_policy
from email.message import Message
from email.parser import BytesParser
from fractions import Fraction
from typing import cast

import pytest

from acquisition.voice import audio_request as request
from acquisition.voice.audio_bound import MAX_INPUT_BYTES, MAX_SAMPLES, DecodeFacts, NormalizedAudio
from acquisition.voice.audio_cost import AudioCostQuote, QualifiedAudioTariff
from runtime.research_runner.audio_provider_catalog import (
    WHISPER_TRANSCRIPTION,
    AudioModelDescriptor,
)

NOW = datetime(2026, 10, 10, tzinfo=UTC)


def _audio(pcm: bytes = b"\x01\x00\x02\x00\x03\x00\x04\x00") -> NormalizedAudio:
    # This independent fixture constructs canonical bytes; it invokes no decoder.
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        len(pcm) + 36,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        16000,
        32000,
        2,
        16,
        b"data",
        len(pcm),
    )
    wav = header + pcm
    facts = DecodeFacts(
        len(wav),
        len(pcm),
        0,
        hashlib.sha256(b"").hexdigest(),
        True,
        True,
        0,
        False,
        False,
        True,
        True,
        True,
        0.25,
        "darwin_local_cpu_only_linux_memory_unproved",
    )
    return NormalizedAudio(
        wav,
        hashlib.sha256(wav).hexdigest(),
        len(wav),
        hashlib.sha256(wav).hexdigest(),
        hashlib.sha256(pcm).hexdigest(),
        len(pcm),
        len(pcm) // 2,
        facts,
    )


def _tariff() -> QualifiedAudioTariff:
    # Explicit synthetic policy qualification; never an active vendor tariff.
    return QualifiedAudioTariff(
        WHISPER_TRANSCRIPTION,
        "USD",
        Fraction(3, 500),
        Fraction(60),
        Fraction(1),
        Fraction(1),
        "synthetic-request-control-v1",
        hashlib.sha256(b"synthetic request-control policy evidence").hexdigest(),
        True,
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 11, 1, tzinfo=UTC),
    )


def _prepare(
    audio: NormalizedAudio | None = None, language: str | None = None
) -> request.PreparedAudioRequest:
    return request.prepare_audio_request(
        _audio() if audio is None else audio,
        WHISPER_TRANSCRIPTION,
        _tariff(),
        now=NOW,
        language=language,
    )


def _parts(prepared: request.PreparedAudioRequest) -> list[Message[str, str]]:
    message = BytesParser(Message, policy=mime_policy.compat32).parsebytes(
        b"MIME-Version: 1.0\r\nContent-Type: "
        + prepared.content_type.encode("ascii")
        + b"\r\n\r\n"
        + prepared.body
    )
    assert message.is_multipart()
    assert not message.defects
    parts = [part for part in message.walk() if not part.is_multipart()]
    assert all(not part.defects for part in parts)
    return parts


@pytest.mark.parametrize("language", [None, "en", "ar", "zz"])
def test_independent_parser_confirms_canonical_field_order_and_exact_wav(
    language: str | None,
) -> None:
    audio, tariff = _audio(), _tariff()
    prepared = request.prepare_audio_request(
        audio, WHISPER_TRANSCRIPTION, tariff, now=NOW, language=language
    )
    parts = _parts(prepared)
    expected = ["model", "response_format"] + ([] if language is None else ["language"]) + ["file"]
    assert [part.get_param("name", header="content-disposition") for part in parts] == expected
    assert len(parts) == len(expected)
    assert parts[0].get_payload(decode=True) == b"whisper-1"
    assert parts[1].get_payload(decode=True) == b"verbose_json"
    if language is not None:
        assert parts[2].get_payload(decode=True) == language.encode("ascii")
    assert parts[-1].get_filename() == "audio.wav"
    assert parts[-1].get_content_type() == "audio/wav"
    assert parts[-1].get_payload(decode=True) == audio.wav
    assert prepared.method == "POST"
    assert prepared.endpoint == "https://api.openai.com"
    assert prepared.request_path == "/v1/audio/transcriptions"
    assert prepared.byte_count == len(prepared.body)
    assert prepared.body_sha256 == hashlib.sha256(prepared.body).hexdigest()
    assert prepared.content_type == "multipart/form-data; boundary=" + prepared.boundary
    assert prepared.boundary.isascii() and len(prepared.boundary) <= 70
    delimiter = b"--" + prepared.boundary.encode("ascii")
    assert prepared.body.count(delimiter) == len(parts) + 1
    assert prepared.body.endswith(delimiter + b"--\r\n")
    assert prepared.body.count(delimiter + b"--\r\n") == 1
    assert prepared.quote.wav_sha256 == audio.wav_sha256
    assert prepared.quote.tariff_sha256 == tariff.digest
    assert prepared.quote.reserved_cents == 1
    request.validate_audio_request(
        prepared, audio, WHISPER_TRANSCRIPTION, tariff, now=NOW, language=language
    )


def test_deterministic_bytes_and_distinct_audio_and_language_bindings() -> None:
    first, same = _prepare(), _prepare()
    language = _prepare(language="en")
    changed_audio = _prepare(_audio(b"\x0a\x00\x0b\x00"))
    assert first == same
    assert first.body == same.body and first.boundary == same.boundary
    assert len({first.boundary, language.boundary, changed_audio.boundary}) == 3
    assert len({first.body_sha256, language.body_sha256, changed_audio.body_sha256}) == 3
    assert first.quote.audio_binding_sha256 != changed_audio.quote.audio_binding_sha256


def test_binary_crlf_is_preserved_by_independent_mime_decode() -> None:
    audio = _audio(b"\r\n\x00\xff\r\n\xfe\x00")
    prepared = _prepare(audio)
    assert _parts(prepared)[-1].get_payload(decode=True) == audio.wav
    assert audio.wav in prepared.body
    assert "RIFF" not in repr(prepared)


def test_inclusive_normalized_maximum_has_bounded_framing_and_exact_pcm() -> None:
    audio = _audio(b"\x00\x00" * MAX_SAMPLES)
    prepared = _prepare(audio)
    assert len(prepared.body) <= MAX_INPUT_BYTES + 4096
    assert 0 < len(prepared.body) - len(audio.wav) <= 4096
    assert _parts(prepared)[-1].get_payload(decode=True) == audio.wav
    assert prepared.quote.duration_seconds == Fraction(600)
    assert prepared.quote.reserved_cents == 6


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("catalog_id", "other"),
        ("model_id", "whisper-1-alias"),
        ("adapter_kind", "text"),
        ("operation", "translate"),
        ("endpoint", "https://api.openai.com/"),
        ("request_path", "/v1/chat/completions"),
        ("catalog_id", True),
        ("model_id", True),
        ("adapter_kind", True),
        ("operation", True),
        ("endpoint", True),
        ("request_path", True),
    ],
)
def test_every_literal_descriptor_field_is_independently_refused(
    name: str, value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    tariff = _tariff()
    descriptor = replace(WHISPER_TRANSCRIPTION)
    object.__setattr__(descriptor, name, value)

    def permissive_catalog(_catalog_id: str, _model_id: str) -> AudioModelDescriptor:
        return descriptor

    # Even a compromised catalog lookup cannot override the new literal route guard.
    monkeypatch.setattr("acquisition.voice.audio_cost.get_audio_model", permissive_catalog)
    with pytest.raises(request.AudioRequestError, match="unsupported_audio_capability"):
        request.prepare_audio_request(_audio(), descriptor, tariff, now=NOW)


@pytest.mark.parametrize("value", [None, True, "whisper-1", ("openai", "whisper-1")])
def test_wrong_descriptor_types_are_refused(value: object) -> None:
    with pytest.raises(request.AudioRequestError, match="unsupported_audio_capability"):
        request.prepare_audio_request(
            _audio(), cast(AudioModelDescriptor, value), _tariff(), now=NOW
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "e",
        "eng",
        "EN",
        "en-US",
        "en\r\nX: a",
        "e\x00",
        "éñ",
        "عرب",
        "e1",
        " en",
        "en ",
        True,
        1,
        b"en",
        [],
    ],
)
def test_language_injections_unicode_and_wrong_types_are_refused(value: object) -> None:
    with pytest.raises(request.AudioRequestError, match="invalid_audio_language"):
        _prepare(language=cast(str, value))


@pytest.mark.parametrize("value", [None, True, "2026-10-10", datetime(2026, 10, 10)])
def test_current_clock_requires_actual_aware_datetime(value: object) -> None:
    with pytest.raises(request.AudioRequestError):
        request.prepare_audio_request(
            _audio(), WHISPER_TRANSCRIPTION, _tariff(), now=cast(datetime, value)
        )


def test_missing_server_tariff_is_refused_without_defaults() -> None:
    with pytest.raises(request.AudioRequestError, match="tariff_required"):
        request.prepare_audio_request(_audio(), WHISPER_TRANSCRIPTION, None, now=NOW)


@pytest.mark.parametrize(
    "instant", [datetime(2026, 9, 30, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)]
)
def test_not_yet_effective_or_exactly_expired_tariff_is_refused(instant: datetime) -> None:
    with pytest.raises(request.AudioRequestError, match="tariff_not_current"):
        request.prepare_audio_request(_audio(), WHISPER_TRANSCRIPTION, _tariff(), now=instant)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("qualified", False),
        ("currency", "EUR"),
        ("rate_usd", Fraction(1)),
        ("unit_seconds", Fraction(1)),
        ("quantum_seconds", Fraction(2)),
        ("minimum_seconds", Fraction(2)),
        ("version", "altered"),
        ("qualification_sha256", "0" * 64),
        ("digest", "0" * 64),
        ("effective_at", datetime(2026, 10, 11, tzinfo=UTC)),
        ("expires_at", datetime(2026, 9, 30, tzinfo=UTC)),
        ("capability", object()),
    ],
)
def test_reflected_server_policy_is_freshly_revalidated(name: str, value: object) -> None:
    tariff = _tariff()
    object.__setattr__(tariff, name, value)
    with pytest.raises(request.AudioRequestError):
        request.prepare_audio_request(_audio(), WHISPER_TRANSCRIPTION, tariff, now=NOW)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("wav", b"RIFF altered"),
        ("source_sha256", "invalid"),
        ("source_bytes", True),
        ("wav_sha256", "0" * 64),
        ("pcm_sha256", "0" * 64),
        ("pcm_bytes", 1),
        ("sample_count", True),
        ("facts", object()),
    ],
)
def test_reflected_normalized_audio_is_freshly_revalidated(name: str, value: object) -> None:
    audio = _audio()
    object.__setattr__(audio, name, value)
    with pytest.raises(request.AudioRequestError):
        _prepare(audio)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("body", b"changed"),
        ("body_sha256", "0" * 64),
        ("content_type", "multipart/form-data; boundary=other\r\nX: a"),
        ("boundary", "other"),
        ("byte_count", True),
        ("method", "GET"),
        ("endpoint", "https://example.invalid"),
        ("request_path", "/v1/chat/completions"),
        ("language", "en"),
        ("quote", object()),
    ],
)
def test_every_reflected_prepared_field_is_refused(name: str, value: object) -> None:
    prepared = _prepare()
    object.__setattr__(prepared, name, value)
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, _tariff(), now=NOW
        )


@pytest.mark.parametrize(
    "name",
    [
        "audio_binding_sha256",
        "source_sha256",
        "wav_sha256",
        "pcm_sha256",
        "sample_count",
        "duration_seconds",
        "capability",
        "capability_sha256",
        "tariff_version",
        "tariff_sha256",
        "qualification_sha256",
        "currency",
        "rate_usd",
        "unit_seconds",
        "quantum_seconds",
        "minimum_seconds",
        "billable_seconds",
        "exact_usd",
        "reserved_cents",
    ],
)
def test_every_nested_quote_binding_is_refused_with_exact_types(name: str) -> None:
    prepared = _prepare()
    original: object = getattr(prepared.quote, name)
    if type(original) is str:
        changed: object = "tampered"
    elif type(original) is int:
        changed = True
    elif isinstance(original, Fraction):
        changed = float(original)
    else:
        changed = object()
    object.__setattr__(prepared.quote, name, changed)
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, _tariff(), now=NOW
        )


def test_reflected_body_and_matching_digest_still_cannot_replace_authoritative_bytes() -> None:
    prepared = _prepare()
    changed = prepared.body + b"extra"
    object.__setattr__(prepared, "body", changed)
    object.__setattr__(prepared, "body_sha256", hashlib.sha256(changed).hexdigest())
    object.__setattr__(prepared, "byte_count", len(changed))
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, _tariff(), now=NOW
        )


@pytest.mark.parametrize("value", [None, True, {}, b"body", ("POST",)])
def test_wrong_prepared_types_are_refused(value: object) -> None:
    with pytest.raises(request.AudioRequestError, match="invalid_prepared_audio_request"):
        request.validate_audio_request(
            cast(request.PreparedAudioRequest, value),
            _audio(),
            WHISPER_TRANSCRIPTION,
            _tariff(),
            now=NOW,
        )


@pytest.mark.parametrize("name", ["body", "quote"])
def test_deleted_reflected_slots_are_refused(name: str) -> None:
    prepared = _prepare()
    object.__delattr__(prepared, name)
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, _tariff(), now=NOW
        )


def test_current_expiry_is_checked_again_when_validating_prepared_value() -> None:
    prepared = _prepare()
    with pytest.raises(request.AudioRequestError, match="tariff_not_current"):
        request.validate_audio_request(
            prepared,
            _audio(),
            WHISPER_TRANSCRIPTION,
            _tariff(),
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )


def test_changed_authoritative_audio_language_and_tariff_refuse_old_request() -> None:
    prepared, tariff = _prepare(), _tariff()
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(b"\x05\x00"), WHISPER_TRANSCRIPTION, tariff, now=NOW
        )
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, tariff, now=NOW, language="en"
        )
    changed_tariff = replace(tariff, version="synthetic-request-control-v2")
    with pytest.raises(request.AudioRequestError, match="audio_request_binding_mismatch"):
        request.validate_audio_request(
            prepared, _audio(), WHISPER_TRANSCRIPTION, changed_tariff, now=NOW
        )


def test_real_framing_marker_in_valid_pcm_is_refused_at_public_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = "asr1-" + "d" * 64
    pcm = b"\r\n--" + boundary.encode("ascii") + b"\r\n"
    if len(pcm) % 2:
        pcm += b"\x00"

    def selected_collision(_quote: AudioCostQuote, _language: str | None) -> str:
        return boundary

    # Force the cryptographically improbable collision, then exercise the public
    # producer against actual valid WAV payload bytes rather than a helper call.
    monkeypatch.setattr(request, "_boundary", selected_collision)
    with pytest.raises(request.AudioRequestError, match="audio_framing_collision"):
        _prepare(_audio(pcm))


@pytest.mark.parametrize("name", ["MAX_FRAMING_BYTES", "MAX_REQUEST_BYTES"])
def test_public_producer_refuses_when_framing_or_output_cannot_fit(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lower only an owned test's local cap to prove the pre-allocation refusal.
    monkeypatch.setattr(request, name, 1)
    with pytest.raises(request.AudioRequestError, match="audio_request_too_large"):
        _prepare()
