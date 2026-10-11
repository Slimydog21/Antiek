"""Real policy/quote controls with synthetic PCM, without native or invoice proof."""

import hashlib
import io
import json
import wave
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from fractions import Fraction
from typing import cast

import pytest

from acquisition.voice import audio_tariff_policy
from acquisition.voice.audio_bound import DecodeFacts, NormalizedAudio
from acquisition.voice.audio_cost import AudioCostError, QualifiedAudioTariff, quote_audio_cost
from runtime.research_runner.audio_provider_catalog import WHISPER_TRANSCRIPTION

EFFECTIVE = datetime(2026, 10, 10, 6, 43, 40, 914939, tzinfo=UTC)
EXPIRY = datetime(2026, 11, 9, 6, 43, 40, 914939, tzinfo=UTC)
QUALIFICATION = "4caeec474aa5fed2067baac246220754d2061fb584236f4451294b7c0fc83999"
DIGEST = "36d37dbe6682a3083d1d03f3ce4d75cde76143d7312564f64251ef675c023151"


def _audio(samples: int) -> NormalizedAudio:
    pcm = (123).to_bytes(2, "little", signed=True) * samples
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(pcm)
    wav = output.getvalue()
    # Complete synthetic facts only. No FFmpeg, native limit or provider was used.
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


def test_exact_server_approval_terms_and_independent_digest() -> None:
    policy = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    expected = {
        "capability": asdict(WHISPER_TRANSCRIPTION),
        "currency": "USD",
        "rate_usd": [3, 500],
        "unit_seconds": [60, 1],
        "quantum_seconds": [1, 1],
        "minimum_seconds": [1, 1],
        "version": "whisper-transcribe.local-reservation.20261010.v1",
        "qualification_sha256": QUALIFICATION,
        "qualified": True,
        "effective_at": EFFECTIVE.isoformat(),
        "expires_at": EXPIRY.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert policy.capability == WHISPER_TRANSCRIPTION
    assert policy.currency == "USD"
    assert policy.rate_usd == Fraction(3, 500)
    assert policy.unit_seconds == Fraction(60)
    assert policy.quantum_seconds == Fraction(1)
    assert policy.minimum_seconds == Fraction(1)
    assert policy.version == expected["version"]
    assert policy.qualification_sha256 == QUALIFICATION
    assert policy.qualified is True
    assert policy.effective_at == EFFECTIVE
    assert policy.expires_at == EXPIRY
    assert policy.digest == digest == DIGEST


@pytest.mark.parametrize(
    ("instant", "current"),
    [
        (EFFECTIVE - timedelta(microseconds=1), False),
        (EFFECTIVE, True),
        (EFFECTIVE + timedelta(microseconds=1), True),
        (EXPIRY - timedelta(microseconds=1), True),
        (EXPIRY, False),
        (EXPIRY + timedelta(microseconds=1), False),
    ],
)
def test_exact_effective_and_expiry_boundaries(instant: datetime, current: bool) -> None:
    if current:
        policy = audio_tariff_policy.current_audio_tariff(now=instant)
        assert policy.effective_at == EFFECTIVE
        assert policy.expires_at == EXPIRY
        assert policy.digest == DIGEST
    else:
        with pytest.raises(AudioCostError, match="^tariff_not_current$"):
            audio_tariff_policy.current_audio_tariff(now=instant)


def test_aware_timezone_and_repeated_calls_do_not_renew_or_share_mutable_policy() -> None:
    shifted = EFFECTIVE.astimezone(timezone(timedelta(hours=3)))
    first = audio_tariff_policy.current_audio_tariff(now=shifted)
    later = audio_tariff_policy.current_audio_tariff(now=EXPIRY - timedelta(microseconds=1))
    assert first is not later
    assert first == later
    assert later.effective_at == EFFECTIVE
    assert later.expires_at == EXPIRY
    object.__setattr__(first, "qualified", False)
    untouched = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    assert untouched.qualified is True
    assert untouched.digest == DIGEST
    with pytest.raises(AudioCostError, match="^tariff_not_current$"):
        audio_tariff_policy.current_audio_tariff(now=EXPIRY + timedelta(days=100))


def test_clock_is_required_without_an_ambient_default() -> None:
    accessor = cast(Callable[..., QualifiedAudioTariff], audio_tariff_policy.current_audio_tariff)
    with pytest.raises(TypeError):
        accessor()


@pytest.mark.parametrize(
    "instant",
    [
        None,
        True,
        1,
        1.0,
        float("nan"),
        float("inf"),
        float("-inf"),
        "2026-10-10T06:43:40Z",
        object(),
        datetime(2026, 10, 10),
        date(2026, 10, 10),
    ],
)
def test_invalid_or_naive_clock_refuses_value_free(instant: object) -> None:
    with pytest.raises(AudioCostError) as caught:
        audio_tariff_policy.current_audio_tariff(now=cast(datetime, instant))
    assert caught.value.code == "invalid_policy_clock"
    assert str(caught.value) == "invalid_policy_clock"
    assert caught.value.__cause__ is None


class _InvalidTimezone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        raise ValueError("private timezone failure must not escape")

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


def test_invalid_timezone_refuses_without_raw_exception_detail() -> None:
    with pytest.raises(AudioCostError, match="^invalid_policy_clock$") as caught:
        audio_tariff_policy.current_audio_tariff(
            now=datetime(2026, 10, 10, tzinfo=_InvalidTimezone())
        )
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("samples", "rounded", "usd", "cents"),
    [
        (1, 1, Fraction(1, 10_000), 1),
        (8_000, 1, Fraction(1, 10_000), 1),
        (16_000, 1, Fraction(1, 10_000), 1),
        (16_001, 2, Fraction(1, 5_000), 1),
        (1_600_000, 100, Fraction(1, 100), 1),
        (1_600_001, 101, Fraction(101, 10_000), 2),
        (9_600_000, 600, Fraction(3, 50), 6),
    ],
)
def test_useful_real_quote_with_conservative_local_rounding(
    samples: int, rounded: int, usd: Fraction, cents: int
) -> None:
    clip = _audio(samples)
    policy = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    quote = quote_audio_cost(clip, WHISPER_TRANSCRIPTION, policy, now=EFFECTIVE)
    assert quote.duration_seconds == Fraction(samples, 16_000)
    assert quote.billable_seconds == Fraction(rounded)
    assert quote.exact_usd == usd
    assert quote.reserved_cents == cents
    assert quote.tariff_sha256 == DIGEST
    assert quote.qualification_sha256 == QUALIFICATION
    assert quote.audio_binding_sha256
    assert quote.pcm_sha256 == clip.pcm_sha256
    assert quote.wav_sha256 == clip.wav_sha256
    assert quote.sample_count == samples


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capability", None),
        ("currency", "EUR"),
        ("rate_usd", Fraction(1, 100)),
        ("rate_usd", float("nan")),
        ("unit_seconds", Fraction(1)),
        ("quantum_seconds", Fraction(2)),
        ("minimum_seconds", Fraction(2)),
        ("minimum_seconds", None),
        ("version", "different-valid-version"),
        ("qualification_sha256", "a" * 64),
        ("qualified", False),
        ("qualified", 1),
        ("effective_at", EFFECTIVE - timedelta(days=1)),
        ("effective_at", datetime(2026, 10, 10)),
        ("expires_at", EXPIRY + timedelta(days=1)),
        ("expires_at", EFFECTIVE + timedelta(seconds=1)),
        ("digest", "b" * 64),
        ("digest", None),
    ],
)
def test_reflected_terms_or_qualification_refuse_even_otherwise_valid_changes(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    changed = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    object.__setattr__(changed, field, value)
    monkeypatch.setattr(audio_tariff_policy, "_SERVER_POLICY", changed)
    with pytest.raises(AudioCostError) as caught:
        audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    assert caught.value.code == "server_audio_tariff_unavailable"
    assert str(caught.value) == "server_audio_tariff_unavailable"
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "field",
    [
        "capability",
        "currency",
        "rate_usd",
        "unit_seconds",
        "quantum_seconds",
        "minimum_seconds",
        "version",
        "qualification_sha256",
        "qualified",
        "effective_at",
        "expires_at",
        "digest",
    ],
)
def test_deleted_reflected_policy_fields_refuse_value_free(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    changed = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    object.__delattr__(changed, field)
    monkeypatch.setattr(audio_tariff_policy, "_SERVER_POLICY", changed)
    with pytest.raises(AudioCostError, match="^server_audio_tariff_unavailable$"):
        audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)


@pytest.mark.parametrize("missing", [None, False, object(), "not a policy"])
def test_missing_or_wrong_policy_has_no_fallback(
    monkeypatch: pytest.MonkeyPatch, missing: object
) -> None:
    monkeypatch.setattr(audio_tariff_policy, "_SERVER_POLICY", missing)
    with pytest.raises(AudioCostError, match="^server_audio_tariff_unavailable$"):
        audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)


def test_absent_server_policy_refuses_instead_of_rebuilding_or_renewing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(audio_tariff_policy, "_SERVER_POLICY")
    with pytest.raises(AudioCostError, match="^server_audio_tariff_unavailable$"):
        audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)


@pytest.mark.parametrize(
    "field",
    ["catalog_id", "model_id", "adapter_kind", "operation", "endpoint", "request_path"],
)
def test_unrelated_capability_cannot_use_the_server_tariff(field: str) -> None:
    other = replace(WHISPER_TRANSCRIPTION)
    object.__setattr__(other, field, "unsupported")
    policy = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    with pytest.raises(AudioCostError, match="^unsupported_audio_capability$"):
        quote_audio_cost(_audio(1), other, policy, now=EFFECTIVE)


def test_quote_rechecks_fixed_expiry_after_selection() -> None:
    policy = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    with pytest.raises(AudioCostError, match="^tariff_not_current$"):
        quote_audio_cost(_audio(1), WHISPER_TRANSCRIPTION, policy, now=EXPIRY)


def test_resealed_changed_terms_still_refuse_the_fixed_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    changed = replace(current, rate_usd=Fraction(1, 100))
    assert changed.digest != DIGEST
    monkeypatch.setattr(audio_tariff_policy, "_SERVER_POLICY", changed)
    with pytest.raises(AudioCostError, match="^server_audio_tariff_unavailable$"):
        audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)


def test_resealed_lifetime_cannot_extend_the_dated_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = audio_tariff_policy.current_audio_tariff(now=EFFECTIVE)
    changed = replace(
        current,
        effective_at=EFFECTIVE + timedelta(days=1),
        expires_at=EXPIRY + timedelta(days=1),
    )
    assert changed.digest != DIGEST
    monkeypatch.setattr(audio_tariff_policy, "_SERVER_POLICY", changed)
    with pytest.raises(AudioCostError, match="^server_audio_tariff_unavailable$"):
        audio_tariff_policy.current_audio_tariff(now=EXPIRY)
