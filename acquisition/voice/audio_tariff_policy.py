"""Fixed server reservation estimate; not an invoice rule or permission to send."""

from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction

from acquisition.voice.audio_cost import AudioCostError, QualifiedAudioTariff
from runtime.research_runner.audio_provider_catalog import WHISPER_TRANSCRIPTION

# Root's dated approval fixes this lifetime. A caller cannot renew it with its clock.
# $0.006/min is dated provider evidence. One-second quantum/minimum are the
# explicitly approved conservative local reservation policy, not vendor billing rules.
_SERVER_POLICY = QualifiedAudioTariff(
    WHISPER_TRANSCRIPTION,
    "USD",
    Fraction(3, 500),
    Fraction(60),
    Fraction(1),
    Fraction(1),
    "whisper-transcribe.local-reservation.20261010.v1",
    "4caeec474aa5fed2067baac246220754d2061fb584236f4451294b7c0fc83999",
    True,
    datetime(2026, 10, 10, 6, 43, 40, 914939, tzinfo=UTC),
    datetime(2026, 11, 9, 6, 43, 40, 914939, tzinfo=UTC),
)
_APPROVAL_DIGEST = "36d37dbe6682a3083d1d03f3ce4d75cde76143d7312564f64251ef675c023151"


def current_audio_tariff(*, now: datetime) -> QualifiedAudioTariff:
    """Return this fixed approval only while current, with an explicit server clock.

    The later worker must separately acquire the selected account credential,
    approved budget, durable operation/send authority and qualified result evidence.
    Public callers cannot supply tariff terms. This accessor cannot settle usage.
    """
    try:
        if type(now) is not datetime or now.utcoffset() is None:
            raise AudioCostError("invalid_policy_clock")
        instant = now.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as _error:
        raise AudioCostError("invalid_policy_clock") from None

    policy = globals().get("_SERVER_POLICY")
    if type(policy) is not QualifiedAudioTariff:
        raise AudioCostError("server_audio_tariff_unavailable")
    try:
        # Revalidation refuses missing/reflected fields, including otherwise valid
        # changed terms. Return a fresh value so callers cannot retire the source.
        validated = replace(policy)
        if (
            type(policy.digest) is not str
            or policy.digest != _APPROVAL_DIGEST
            or validated.digest != _APPROVAL_DIGEST
        ):
            raise AudioCostError("server_audio_tariff_unavailable")
    except (AttributeError, TypeError, ValueError, OverflowError) as _error:
        raise AudioCostError("server_audio_tariff_unavailable") from None
    if not validated.effective_at <= instant < validated.expires_at:
        raise AudioCostError("tariff_not_current")
    return validated
