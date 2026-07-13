from __future__ import annotations

from pathlib import Path

import pytest

from substrate.multimedia.production_registration import (
    MultimediaProductionRegistrationError,
    MultimediaProductionRegistrationRequest,
    register_multimedia_production,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaProductionLink,
    SteeringRequest,
)
from substrate.multimedia.verified_playback import PlaybackMediaMetadata


class FakePlayback:
    def metadata(self, *, asset_id: str, revision_id: str) -> PlaybackMediaMetadata:
        return PlaybackMediaMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256="c" * 64,
            duration_seconds=90.0,
            video_sha256="a" * 64,
            audio_sha256="b" * 64,
            video_size_bytes=100,
            audio_size_bytes=80,
            width_px=1280,
            height_px=720,
            chapter_ids=("chapter-1",),
        )


def _store(tmp_path: Path, *, mode: str = "video") -> tuple[MultimediaAssetStore, str]:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    record = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Verified production",
            target_minutes=15,
            mode=mode,
            route_policy="balanced",
        ),
        owner_id="owner-1",
    )
    return store, record.asset.asset_id


def test_registration_attaches_exact_verified_metadata_and_replays(tmp_path: Path) -> None:
    store, asset_id = _store(tmp_path)
    store.approve_dry_run(asset_id, owner_id="owner-1")
    request = MultimediaProductionRegistrationRequest(expected_revision_id="rev-1")

    first = register_multimedia_production(
        asset_id, request, owner_id="owner-1", store=store, playback=FakePlayback()  # type: ignore[arg-type]
    )
    assert first.production_link is not None
    assert first.production_link.receipt_sha256 == "c" * 64
    assert first.production_link.owner_identity_digest == first.asset.owner_user_id
    assert first.summary().production_ready is True

    replay = register_multimedia_production(
        asset_id, request, owner_id="owner-1", store=store, playback=FakePlayback()  # type: ignore[arg-type]
    )
    assert replay.production_link == first.production_link


def test_registration_rejects_foreign_stale_unready_and_audio_assets(tmp_path: Path) -> None:
    store, asset_id = _store(tmp_path)
    with pytest.raises(MultimediaProductionRegistrationError, match="unavailable"):
        register_multimedia_production(
            asset_id,
            MultimediaProductionRegistrationRequest(expected_revision_id="rev-1"),
            owner_id="owner-2",
            store=store,
            playback=FakePlayback(),  # type: ignore[arg-type]
        )
    with pytest.raises(MultimediaProductionRegistrationError, match="ready"):
        register_multimedia_production(
            asset_id,
            MultimediaProductionRegistrationRequest(expected_revision_id="rev-1"),
            owner_id="owner-1",
            store=store,
            playback=FakePlayback(),  # type: ignore[arg-type]
        )
    store.approve_dry_run(asset_id, owner_id="owner-1")
    with pytest.raises(MultimediaProductionRegistrationError, match="current"):
        register_multimedia_production(
            asset_id,
            MultimediaProductionRegistrationRequest(expected_revision_id="rev-old"),
            owner_id="owner-1",
            store=store,
            playback=FakePlayback(),  # type: ignore[arg-type]
        )

    audio_store, audio_id = _store(tmp_path / "audio", mode="audio")
    audio_store.approve_dry_run(audio_id, owner_id="owner-1")
    with pytest.raises(MultimediaProductionRegistrationError, match="video asset"):
        register_multimedia_production(
            audio_id,
            MultimediaProductionRegistrationRequest(expected_revision_id="rev-1"),
            owner_id="owner-1",
            store=audio_store,
            playback=FakePlayback(),  # type: ignore[arg-type]
        )


def test_conflicting_existing_link_is_not_replaced(tmp_path: Path) -> None:
    store, asset_id = _store(tmp_path)
    ready = store.approve_dry_run(asset_id, owner_id="owner-1")
    conflicting = MultimediaProductionLink(
        owner_identity_digest=ready.asset.owner_user_id,
        asset_id=asset_id,
        revision_id="rev-1",
        receipt_sha256="f" * 64,
        video_sha256="e" * 64,
        audio_sha256="d" * 64,
        duration_seconds=60,
        width_px=1280,
        height_px=720,
        chapter_ids=("chapter-1",),
    )
    store.attach_production_link(
        asset_id, conflicting, expected_revision_id="rev-1", owner_id="owner-1"
    )
    with pytest.raises(MultimediaProductionRegistrationError, match="conflicts"):
        register_multimedia_production(
            asset_id,
            MultimediaProductionRegistrationRequest(expected_revision_id="rev-1"),
            owner_id="owner-1",
            store=store,
            playback=FakePlayback(),  # type: ignore[arg-type]
        )
    assert store.get(asset_id, owner_id="owner-1").production_link == conflicting

    forged = store.get(asset_id, owner_id="owner-1").model_copy(
        update={
            "production_link": conflicting.model_copy(
                update={"owner_identity_digest": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="identity"):
        store.save(forged, owner_id="owner-1")

    steered = store.apply_steering(
        asset_id,
        SteeringRequest(prompt="Make the opening more concrete"),
        owner_id="owner-1",
    )
    assert steered.asset.revision_id != "rev-1"
    assert steered.production_link is None
