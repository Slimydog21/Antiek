"""Register a verified audio-only receipt on its still-current asset revision."""

from __future__ import annotations

from dataclasses import dataclass

from .read_model import (
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaAudioProductionLink,
)
from .verified_audio_playback import VerifiedAudioPlaybackRuntime
from .verified_playback import VerifiedPlaybackError


class MultimediaAudioRegistrationError(RuntimeError):
    """An audible receipt cannot become current asset authority."""


@dataclass(frozen=True)
class MultimediaAudioRegistrationRequest:
    expected_revision_id: str


def register_multimedia_audio_production(
    asset_id: str,
    request: MultimediaAudioRegistrationRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    playback: VerifiedAudioPlaybackRuntime,
) -> MultimediaAssetRecord:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except (KeyError, ValueError) as exc:
        raise MultimediaAudioRegistrationError("multimedia audio asset is unavailable") from exc
    if record.asset.revision_id != request.expected_revision_id:
        raise MultimediaAudioRegistrationError("multimedia audio revision is not current")
    if str(record.asset.status) != "ready":
        raise MultimediaAudioRegistrationError(
            "multimedia audio registration requires a ready asset"
        )
    if record.mode != "audio" or str(record.asset.kind) != "audio_experience":
        raise MultimediaAudioRegistrationError(
            "multimedia audio registration requires an audio asset"
        )
    try:
        metadata = playback.metadata(
            asset_id=asset_id,
            revision_id=request.expected_revision_id,
            owner_digest=str(record.asset.owner_user_id),
        )
    except VerifiedPlaybackError as exc:
        raise MultimediaAudioRegistrationError(
            "verified multimedia audio production is unavailable"
        ) from exc
    link = MultimediaAudioProductionLink(
        owner_identity_digest=str(record.asset.owner_user_id),
        asset_id=metadata.asset_id,
        revision_id=metadata.revision_id,
        receipt_sha256=metadata.receipt_sha256,
        audio_sha256=metadata.audio_sha256,
        duration_seconds=metadata.duration_seconds,
        chapter_ids=metadata.chapter_ids,
        retention_marker_count=metadata.retention_marker_count,
        learned_claim_count=metadata.learned_claim_count,
    )
    try:
        return store.attach_audio_production_link(
            asset_id,
            link,
            expected_revision_id=request.expected_revision_id,
            owner_id=owner_id,
        )
    except (KeyError, ValueError) as exc:
        raise MultimediaAudioRegistrationError(str(exc)) from exc


__all__ = [
    "MultimediaAudioRegistrationError",
    "MultimediaAudioRegistrationRequest",
    "register_multimedia_audio_production",
]
