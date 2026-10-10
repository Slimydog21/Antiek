"""Synthetic server tariffs and PCM facts exercise quotes, not vendor billing/native proof."""

import hashlib
import io
import wave
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import cast

import pytest

from acquisition.voice.audio_bound import MAX_SAMPLES, DecodeFacts, NormalizedAudio
from acquisition.voice.audio_cost import (
    AudioCostError,
    QualifiedAudioTariff,
    quote_audio_cost,
)
from runtime.research_runner.audio_provider_catalog import WHISPER_TRANSCRIPTION

NOW = datetime(2026, 10, 9, tzinfo=UTC)
EXPIRY = datetime(2027, 2, 26, tzinfo=UTC)
QUALIFICATION = hashlib.sha256(b"synthetic server policy; not vendor billing evidence").hexdigest()


def audio(samples: int = 1, *, value: int = 0) -> NormalizedAudio:
    pcm = value.to_bytes(2, "little", signed=True) * samples
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(pcm)
    wav = output.getvalue()
    # Complete synthetic facts; no decoder, process, provider or native limits were exercised.
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
        0.1,
        "darwin_local_cpu_only_linux_memory_unproved",
    )
    return NormalizedAudio(
        wav,
        hashlib.sha256(wav).hexdigest(),
        len(wav),
        hashlib.sha256(wav).hexdigest(),
        hashlib.sha256(pcm).hexdigest(),
        len(pcm),
        samples,
        facts,
    )


def tariff() -> QualifiedAudioTariff:
    # The observed $0.006/min rate is not an active policy. This fixture declares
    # synthetic one-second minimum/quantum explicitly; neither is a vendor claim.
    return QualifiedAudioTariff(
        WHISPER_TRANSCRIPTION,
        "USD",
        Fraction(3, 500),
        Fraction(60),
        Fraction(1),
        Fraction(1),
        "synthetic-v1",
        QUALIFICATION,
        True,
        NOW,
        EXPIRY,
    )


def test_smallest_paid_clip_has_exact_duration_and_positive_reservation() -> None:
    clip, policy = audio(), tariff()
    result = quote_audio_cost(clip, WHISPER_TRANSCRIPTION, policy, now=NOW)
    assert result.duration_seconds == Fraction(1, 16_000)
    assert result.billable_seconds == 1
    assert result.exact_usd == Fraction(1, 10_000)
    assert result.reserved_cents == 1
    assert result.currency == "USD"
    assert result.tariff_sha256 == policy.digest
    assert result.qualification_sha256 == QUALIFICATION
    assert result.wav_sha256 == clip.wav_sha256
    assert result.pcm_sha256 == clip.pcm_sha256
    assert result.source_sha256 == clip.source_sha256
    assert result.sample_count == clip.sample_count
    assert result.capability == WHISPER_TRANSCRIPTION


@pytest.mark.parametrize(
    ("samples", "rate", "minimum", "quantum", "rounded", "usd", "cents"),
    [
        (8_000, Fraction(1), Fraction(1, 4), Fraction(1, 4), Fraction(1, 2), Fraction(1, 2), 50),
        (1, Fraction(1), Fraction(1, 4), Fraction(1, 4), Fraction(1, 4), Fraction(1, 4), 25),
        (1, Fraction(1, 100), Fraction(3), Fraction(2), Fraction(4), Fraction(1, 25), 4),
        (8_000, Fraction(3, 2), Fraction(1, 3), Fraction(1, 3), Fraction(2, 3), Fraction(1), 100),
        (16_000, Fraction(1, 100), Fraction(1), Fraction(1), Fraction(1), Fraction(1, 100), 1),
        (
            16_000,
            Fraction(10_001, 1_000_000),
            Fraction(1),
            Fraction(1),
            Fraction(1),
            Fraction(10_001, 1_000_000),
            2,
        ),
    ],
)
def test_declared_minimum_quantum_and_cent_rounding(
    samples: int,
    rate: Fraction,
    minimum: Fraction,
    quantum: Fraction,
    rounded: Fraction,
    usd: Fraction,
    cents: int,
) -> None:
    policy = replace(
        tariff(),
        rate_usd=rate,
        unit_seconds=Fraction(1),
        minimum_seconds=minimum,
        quantum_seconds=quantum,
    )
    result = quote_audio_cost(audio(samples), WHISPER_TRANSCRIPTION, policy, now=NOW)
    assert result.billable_seconds == rounded
    assert result.exact_usd == usd
    assert result.reserved_cents == cents
    assert result.rate_usd == rate
    assert result.minimum_seconds == minimum
    assert result.quantum_seconds == quantum
    assert result.unit_seconds == 1


def test_signed64_cent_boundary_and_overflow() -> None:
    limit = (1 << 63) - 1
    policy = replace(tariff(), rate_usd=Fraction(limit, 100), unit_seconds=Fraction(1))
    result = quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=NOW)
    assert result.reserved_cents == limit
    with pytest.raises(AudioCostError, match="^reservation_overflow$"):
        quote_audio_cost(
            audio(), WHISPER_TRANSCRIPTION, replace(policy, rate_usd=Fraction(limit)), now=NOW
        )


def test_quote_and_policy_seals_bind_changed_audio_terms_and_evidence() -> None:
    policy = tariff()
    first = quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=NOW)
    other = quote_audio_cost(audio(value=1), WHISPER_TRANSCRIPTION, policy, now=NOW)
    changed = replace(policy, version="synthetic-v2", qualification_sha256="1" * 64)
    third = quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, changed, now=NOW)
    assert first.audio_binding_sha256 != other.audio_binding_sha256
    assert first.capability_sha256 == other.capability_sha256
    assert first.tariff_sha256 != third.tariff_sha256
    assert third.tariff_version == "synthetic-v2"
    field_name = "reserved_cents"
    with pytest.raises(FrozenInstanceError):
        setattr(first, field_name, 0)
    field_name = "version"
    with pytest.raises(FrozenInstanceError):
        setattr(policy, field_name, "public caller")


def test_absent_tariff_refuses_without_audio_or_monetary_detail() -> None:
    with pytest.raises(AudioCostError, match="^tariff_required$") as error:
        quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, None, now=NOW)
    assert error.value.code == "tariff_required"


@pytest.mark.parametrize(
    ("field_name", "value", "code"),
    [
        ("qualified", False, "unqualified_tariff"),
        ("qualified", 1, "unqualified_tariff"),
        ("currency", "EUR", "unqualified_tariff"),
        ("version", "", "unqualified_tariff"),
        ("version", " " * 129, "unqualified_tariff"),
        ("qualification_sha256", "unknown", "unqualified_tariff"),
        ("rate_usd", Fraction(0), "invalid_tariff_terms"),
        ("rate_usd", Fraction(-1), "invalid_tariff_terms"),
        ("rate_usd", float("nan"), "invalid_tariff_terms"),
        ("rate_usd", float("inf"), "invalid_tariff_terms"),
        ("rate_usd", 0.006, "invalid_tariff_terms"),
        ("rate_usd", True, "invalid_tariff_terms"),
        ("rate_usd", Fraction(1 << 63), "invalid_tariff_terms"),
        ("rate_usd", Fraction(1, 1 << 63), "invalid_tariff_terms"),
        ("unit_seconds", Fraction(0), "invalid_tariff_terms"),
        ("quantum_seconds", None, "invalid_tariff_terms"),
        ("quantum_seconds", Fraction(0), "invalid_tariff_terms"),
        ("minimum_seconds", None, "invalid_tariff_terms"),
        ("minimum_seconds", Fraction(0), "invalid_tariff_terms"),
        ("effective_at", NOW.replace(tzinfo=None), "invalid_policy_clock"),
        ("expires_at", EXPIRY + timedelta(seconds=1), "invalid_tariff_lifetime"),
        ("expires_at", NOW, "invalid_tariff_lifetime"),
        ("digest", "0" * 64, "tariff_binding_mismatch"),
        ("rate_usd", Fraction(1), "tariff_binding_mismatch"),
        ("version", "reflected", "tariff_binding_mismatch"),
    ],
)
def test_unqualified_unknown_invalid_or_reflected_tariff_refuses(
    field_name: str,
    value: object,
    code: str,
) -> None:
    policy = tariff()
    object.__setattr__(policy, field_name, value)
    with pytest.raises(AudioCostError, match=f"^{code}$"):
        quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=NOW)


def test_policy_effective_inclusive_expiry_exclusive_and_shutdown() -> None:
    policy = tariff()
    assert quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=NOW).reserved_cents == 1
    for instant in (NOW - timedelta(microseconds=1), EXPIRY, EXPIRY + timedelta(days=1)):
        with pytest.raises(AudioCostError, match="^tariff_not_current$"):
            quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=instant)
    with pytest.raises(AudioCostError, match="^invalid_tariff_lifetime$"):
        replace(policy, expires_at=EXPIRY + timedelta(microseconds=1))


def test_timezone_instants_normalize_without_changing_policy_identity() -> None:
    from datetime import timezone

    shifted = NOW.astimezone(timezone(timedelta(hours=3)))
    policy = replace(tariff(), effective_at=shifted)
    assert policy.digest == tariff().digest
    assert quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, policy, now=shifted).reserved_cents == 1


@pytest.mark.parametrize(
    "instant", [NOW.replace(tzinfo=None), float("nan"), float("inf"), True, None]
)
def test_invalid_clock_refuses(instant: object) -> None:
    with pytest.raises(AudioCostError, match="^invalid_policy_clock$"):
        quote_audio_cost(audio(), WHISPER_TRANSCRIPTION, tariff(), now=cast(datetime, instant))


def test_wrong_runtime_input_types_refuse() -> None:
    with pytest.raises(AudioCostError, match="^invalid_normalized_audio$"):
        quote_audio_cost(cast(NormalizedAudio, None), WHISPER_TRANSCRIPTION, tariff(), now=NOW)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("model_id", "gpt-transcribe"),
        ("catalog_id", "foreign"),
        ("endpoint", "https://untrusted.invalid"),
        ("operation", "complete"),
        ("adapter_kind", "text"),
        ("request_path", "/v1/chat/completions"),
    ],
)
def test_unsupported_capability_never_substitutes(field_name: str, value: str) -> None:
    capability = replace(WHISPER_TRANSCRIPTION)
    object.__setattr__(capability, field_name, value)
    with pytest.raises(AudioCostError, match="^unsupported_audio_capability$"):
        quote_audio_cost(audio(), capability, tariff(), now=NOW)
    with pytest.raises(AudioCostError, match="^unsupported_audio_capability$"):
        replace(tariff(), capability=capability)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("sample_count", MAX_SAMPLES + 1),
        ("sample_count", True),
        ("pcm_bytes", 1),
        ("source_bytes", 0),
        ("source_sha256", "private"),
        ("wav_sha256", "0" * 64),
        ("pcm_sha256", "0" * 64),
        ("wav", b"invalid"),
    ],
)
def test_tampered_pcm_and_source_binding_refuses(field_name: str, value: object) -> None:
    clip = audio()
    object.__setattr__(clip, field_name, value)
    with pytest.raises(AudioCostError, match="^invalid_normalized_audio$"):
        quote_audio_cost(clip, WHISPER_TRANSCRIPTION, tariff(), now=NOW)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("reaped", False),
        ("handles_closed", False),
        ("cleanup_complete", False),
        ("stdout_eof", False),
        ("stderr_eof", False),
        ("exit_code", 1),
        ("exit_code", False),
        ("input_bytes_written", 1),
        ("pcm_bytes_read", 1),
        ("stderr_bytes_read", 1),
        ("stderr_sha256", "0" * 64),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", 30.001),
        ("elapsed_seconds", -1.0),
        ("limit_policy", "unknown"),
    ],
)
def test_incomplete_or_invalid_decode_facts_refuse(field_name: str, value: object) -> None:
    clip = audio()
    object.__setattr__(clip.facts, field_name, value)
    with pytest.raises(AudioCostError, match="^invalid_normalized_audio$"):
        quote_audio_cost(clip, WHISPER_TRANSCRIPTION, tariff(), now=NOW)
