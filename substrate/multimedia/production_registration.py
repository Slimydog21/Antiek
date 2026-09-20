"""Durably bind a verified educational-video receipt to its owner asset."""

from __future__ import annotations

from dataclasses import dataclass

from .read_model import MultimediaAssetRecord, MultimediaAssetStore, MultimediaProductionLink
from .verified_playback import VerifiedPlaybackError, VerifiedPlaybackRuntime


class MultimediaProductionRegistrationError(RuntimeError):
    """A production receipt cannot become current asset authority."""


@dataclass(frozen=True)
class MultimediaProductionRegistrationRequest:
    expected_revision_id: str


def register_multimedia_production(
    asset_id: str,
    request: MultimediaProductionRegistrationRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    playback: VerifiedPlaybackRuntime,
) -> MultimediaAssetRecord:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except (KeyError, ValueError) as exc:
        raise MultimediaProductionRegistrationError("multimedia asset is unavailable") from exc
    if record.asset.revision_id != request.expected_revision_id:
        raise MultimediaProductionRegistrationError("multimedia production revision is not current")
    if str(record.asset.status) != "ready":
        raise MultimediaProductionRegistrationError(
            "multimedia production registration requires a ready asset"
        )
    if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
        raise MultimediaProductionRegistrationError(
            "multimedia video production requires a video asset"
        )
    try:
        metadata = playback.metadata(asset_id=asset_id, revision_id=request.expected_revision_id)
    except VerifiedPlaybackError as exc:
        raise MultimediaProductionRegistrationError(
            "verified multimedia production is unavailable"
        ) from exc
    link = MultimediaProductionLink(
        owner_identity_digest=record.asset.owner_user_id,
        asset_id=metadata.asset_id,
        revision_id=metadata.revision_id,
        receipt_sha256=metadata.receipt_sha256,
        video_sha256=metadata.video_sha256,
        audio_sha256=metadata.audio_sha256,
        duration_seconds=metadata.duration_seconds,
        width_px=metadata.width_px,
        height_px=metadata.height_px,
        chapter_ids=metadata.chapter_ids,
    )
    try:
        return store.attach_production_link(
            asset_id,
            link,
            expected_revision_id=request.expected_revision_id,
            owner_id=owner_id,
        )
    except (KeyError, ValueError) as exc:
        raise MultimediaProductionRegistrationError(str(exc)) from exc


__all__ = [
    "MultimediaProductionRegistrationError",
    "MultimediaProductionRegistrationRequest",
    "register_multimedia_production",
]
