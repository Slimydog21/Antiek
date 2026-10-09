"""Exact audio reservation estimates; no tariff defaults or payment/send authority."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fractions import Fraction

from acquisition.voice.audio_bound import (
    MAX_INPUT_BYTES,
    MAX_SAMPLES,
    SAMPLE_RATE_HZ,
    TOTAL_SECONDS,
    DecodeFacts,
    NormalizedAudio,
)
from runtime.research_runner.audio_provider_catalog import (
    AudioModelDescriptor,
    get_audio_model,
)

_MAX_CENTS = (1 << 63) - 1
# Dated model availability evidence, not a price or dispatch permission.
_WHISPER_LATEST_EXPIRY = datetime(2027, 2, 26, tzinfo=UTC)


class AudioCostError(ValueError):
    """Value-free refusal suitable for a later admission boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _instant(value: datetime) -> datetime:
    try:
        if type(value) is not datetime or value.utcoffset() is None:
            raise AudioCostError("invalid_policy_clock")
        return value.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as _error:
        raise AudioCostError("invalid_policy_clock") from None


def _positive(value: Fraction) -> None:
    if (
        type(value) is not Fraction
        or not 0 < value.numerator <= _MAX_CENTS
        or not 0 < value.denominator <= _MAX_CENTS
    ):
        raise AudioCostError("invalid_tariff_terms")


def _capability(value: AudioModelDescriptor) -> None:
    if type(value) is not AudioModelDescriptor:
        raise AudioCostError("unsupported_audio_capability")
    try:
        canonical = get_audio_model(value.catalog_id, value.model_id)
    except ValueError:
        raise AudioCostError("unsupported_audio_capability") from None
    if value != canonical:
        raise AudioCostError("unsupported_audio_capability")


def _ratio(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


@dataclass(frozen=True, slots=True)
class QualifiedAudioTariff:
    """Explicit trusted server policy, never constructed from public request data.

    Qualification identifies the server's policy evidence. It does not attest
    vendor invoicing, account ownership, available funds or permission to send.
    No active policy is supplied by this module.
    """

    capability: AudioModelDescriptor
    currency: str
    rate_usd: Fraction
    unit_seconds: Fraction
    quantum_seconds: Fraction
    minimum_seconds: Fraction
    version: str
    qualification_sha256: str
    qualified: bool
    effective_at: datetime
    expires_at: datetime
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        _capability(self.capability)
        if (
            self.currency != "USD"
            or type(self.currency) is not str
            or type(self.qualified) is not bool
            or not self.qualified
            or type(self.version) is not str
            or not 1 <= len(self.version) <= 128
            or not self.version.isascii()
            or not self.version.strip()
            or not _sha(self.qualification_sha256)
        ):
            raise AudioCostError("unqualified_tariff")
        for value in (
            self.rate_usd,
            self.unit_seconds,
            self.quantum_seconds,
            self.minimum_seconds,
        ):
            _positive(value)
        effective, expires = _instant(self.effective_at), _instant(self.expires_at)
        if not effective < expires <= _WHISPER_LATEST_EXPIRY:
            raise AudioCostError("invalid_tariff_lifetime")
        object.__setattr__(self, "effective_at", effective)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "digest", _digest(self._binding()))

    def _binding(self) -> dict[str, object]:
        return {
            "capability": asdict(self.capability),
            "currency": self.currency,
            "rate_usd": _ratio(self.rate_usd),
            "unit_seconds": _ratio(self.unit_seconds),
            "quantum_seconds": _ratio(self.quantum_seconds),
            "minimum_seconds": _ratio(self.minimum_seconds),
            "version": self.version,
            "qualification_sha256": self.qualification_sha256,
            "qualified": self.qualified,
            "effective_at": self.effective_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AudioCostQuote:
    audio_binding_sha256: str
    source_sha256: str
    wav_sha256: str
    pcm_sha256: str
    sample_count: int
    duration_seconds: Fraction
    capability: AudioModelDescriptor
    capability_sha256: str
    tariff_version: str
    tariff_sha256: str
    qualification_sha256: str
    currency: str
    rate_usd: Fraction
    unit_seconds: Fraction
    quantum_seconds: Fraction
    minimum_seconds: Fraction
    billable_seconds: Fraction
    exact_usd: Fraction
    reserved_cents: int


def _audio_binding(audio: NormalizedAudio) -> str:
    if type(audio) is not NormalizedAudio or type(audio.facts) is not DecodeFacts:
        raise AudioCostError("invalid_normalized_audio")
    facts = audio.facts
    if (
        type(audio.wav) is not bytes
        or type(audio.sample_count) is not int
        or not 1 <= audio.sample_count <= MAX_SAMPLES
        or type(audio.source_bytes) is not int
        or not 1 <= audio.source_bytes <= MAX_INPUT_BYTES
        or type(audio.pcm_bytes) is not int
        or audio.pcm_bytes != audio.sample_count * 2
        or len(audio.wav) != audio.pcm_bytes + 44
        or not all(
            _sha(value)
            for value in (
                audio.source_sha256,
                audio.wav_sha256,
                audio.pcm_sha256,
                facts.stderr_sha256,
            )
        )
        or any(
            type(value) is not int
            for value in (
                facts.input_bytes_written,
                facts.pcm_bytes_read,
                facts.stderr_bytes_read,
                facts.exit_code,
            )
        )
        or facts.stderr_bytes_read != 0
        or facts.stderr_sha256 != hashlib.sha256(b"").hexdigest()
        or any(
            type(value) is not bool
            for value in (
                facts.stdout_eof,
                facts.stderr_eof,
                facts.terminated,
                facts.killed,
                facts.reaped,
                facts.handles_closed,
                facts.cleanup_complete,
            )
        )
        or not facts.reaped
        or not facts.handles_closed
        or type(facts.elapsed_seconds) is not float
        or not math.isfinite(facts.elapsed_seconds)
        or not 0 <= facts.elapsed_seconds <= TOTAL_SECONDS
        or type(facts.limit_policy) is not str
        or facts.limit_policy
        not in ("darwin_local_cpu_only_linux_memory_unproved", "linux_cpu_and_address_space")
    ):
        raise AudioCostError("invalid_normalized_audio")
    try:
        # Recheck the actual producer contract, including canonical WAV and PCM hashes.
        audio.__post_init__()
    except (TypeError, ValueError, AttributeError) as _error:
        raise AudioCostError("invalid_normalized_audio") from None
    return _digest(
        {
            "source_sha256": audio.source_sha256,
            "source_bytes": audio.source_bytes,
            "wav_sha256": audio.wav_sha256,
            "pcm_sha256": audio.pcm_sha256,
            "pcm_bytes": audio.pcm_bytes,
            "sample_count": audio.sample_count,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "facts": asdict(facts),
        }
    )


def _ceil(value: Fraction) -> int:
    return (value.numerator + value.denominator - 1) // value.denominator


def quote_audio_cost(
    audio: NormalizedAudio,
    capability: AudioModelDescriptor,
    policy: QualifiedAudioTariff | None,
    *,
    now: datetime,
) -> AudioCostQuote:
    """Conservatively round a qualified duration estimate to signed64 cents.

    The caller must separately admit owner, budget, durable operation and send.
    This estimate cannot settle actual usage or imply free transcription.
    """
    _capability(capability)
    if type(policy) is not QualifiedAudioTariff:
        raise AudioCostError("tariff_required")
    # A frozen dataclass can still be reflected into; validate a fresh copy and seal.
    validated = QualifiedAudioTariff(
        policy.capability,
        policy.currency,
        policy.rate_usd,
        policy.unit_seconds,
        policy.quantum_seconds,
        policy.minimum_seconds,
        policy.version,
        policy.qualification_sha256,
        policy.qualified,
        policy.effective_at,
        policy.expires_at,
    )
    if not _sha(policy.digest) or policy.digest != validated.digest:
        raise AudioCostError("tariff_binding_mismatch")
    if capability != validated.capability:
        raise AudioCostError("unsupported_audio_capability")
    instant = _instant(now)
    if not validated.effective_at <= instant < validated.expires_at:
        raise AudioCostError("tariff_not_current")
    audio_digest = _audio_binding(audio)
    duration = Fraction(audio.sample_count, SAMPLE_RATE_HZ)
    billable = _ceil(max(duration, validated.minimum_seconds) / validated.quantum_seconds)
    rounded = billable * validated.quantum_seconds
    exact_usd = rounded * validated.rate_usd / validated.unit_seconds
    cents = _ceil(exact_usd * 100)
    if not 1 <= cents <= _MAX_CENTS:
        raise AudioCostError("reservation_overflow")
    return AudioCostQuote(
        audio_digest,
        audio.source_sha256,
        audio.wav_sha256,
        audio.pcm_sha256,
        audio.sample_count,
        duration,
        capability,
        _digest(asdict(capability)),
        validated.version,
        validated.digest,
        validated.qualification_sha256,
        validated.currency,
        validated.rate_usd,
        validated.unit_seconds,
        validated.quantum_seconds,
        validated.minimum_seconds,
        rounded,
        exact_usd,
        cents,
    )
