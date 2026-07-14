from __future__ import annotations

from pathlib import Path

import pytest

from substrate.multimedia.audio_production_registration import (
    MultimediaAudioRegistrationError,
    MultimediaAudioRegistrationRequest,
    register_multimedia_audio_production,
)
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    SteeringPreviewRequest,
)
from substrate.multimedia.verified_audio_playback import (
    AudioLearnedClaimMetadata,
    AudioPlaybackMetadata,
)


class _Playback:
    def metadata(self, *, asset_id: str, revision_id: str, owner_digest: str):  # noqa: ANN201
        return AudioPlaybackMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256="a" * 64,
            audio_sha256="b" * 64,
            audio_size_bytes=100,
            duration_seconds=90,
            chapter_ids=("chapter-1",),
            retention_marker_count=2,
            learned_claim_count=1,
            source_count=1,
            learned_claims=(
                AudioLearnedClaimMetadata(
                    chapter_id="chapter-1",
                    claim_text="Verified claim",
                    source_count=1,
                    follow_up_prompt="Review the source.",
                ),
            ),
        )


def _store(tmp_path: Path, *, mode: str = "audio") -> tuple[MultimediaAssetStore, str]:
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    record = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Verified audible production",
            target_minutes=15,
            mode=mode,
            route_policy="cheapest",
            sources=("Verified audible production uses reviewed source evidence.",),
            selected_arc_ids=("history",),
        ),
        owner_id="owner-1",
    )
    return store, record.asset.asset_id


def test_audio_registration_attaches_exact_metadata_replays_and_steering_clears(
    tmp_path: Path,
) -> None:
    store, asset_id = _store(tmp_path)
    store.approve_dry_run(asset_id, owner_id="owner-1")
    request = MultimediaAudioRegistrationRequest(expected_revision_id="rev-1")
    first = register_multimedia_audio_production(
        asset_id,
        request,
        owner_id="owner-1",
        store=store,
        playback=_Playback(),  # type: ignore[arg-type]
    )
    assert first.production_link is None
    assert first.audio_production_link is not None
    assert first.audio_production_link.audio_sha256 == "b" * 64
    assert first.summary().production_ready is True
    replay = register_multimedia_audio_production(
        asset_id,
        request,
        owner_id="owner-1",
        store=store,
        playback=_Playback(),  # type: ignore[arg-type]
    )
    assert replay.audio_production_link == first.audio_production_link
    steering = SteeringPreviewRequest(
        expected_parent_revision_id=first.asset.revision_id,
        prompt="go deeper on engines in chapter 2",
    )
    preview = store.preview_steering(asset_id, steering, owner_id="owner-1")
    assert preview.status == "ready"
    steered = store.apply_steering_preview(
        asset_id,
        ApplySteeringPreviewRequest(
            **steering.model_dump(),
            preview_token=preview.preview_token,
        ),
        owner_id="owner-1",
    )
    assert steered.audio_production_link is None


def test_audio_registration_rejects_foreign_stale_unready_and_video_assets(
    tmp_path: Path,
) -> None:
    store, asset_id = _store(tmp_path)
    request = MultimediaAudioRegistrationRequest(expected_revision_id="rev-1")
    with pytest.raises(MultimediaAudioRegistrationError, match="unavailable"):
        register_multimedia_audio_production(
            asset_id,
            request,
            owner_id="owner-2",
            store=store,
            playback=_Playback(),  # type: ignore[arg-type]
        )
    with pytest.raises(MultimediaAudioRegistrationError, match="ready"):
        register_multimedia_audio_production(
            asset_id,
            request,
            owner_id="owner-1",
            store=store,
            playback=_Playback(),  # type: ignore[arg-type]
        )
    store.approve_dry_run(asset_id, owner_id="owner-1")
    with pytest.raises(MultimediaAudioRegistrationError, match="current"):
        register_multimedia_audio_production(
            asset_id,
            MultimediaAudioRegistrationRequest(expected_revision_id="old"),
            owner_id="owner-1",
            store=store,
            playback=_Playback(),  # type: ignore[arg-type]
        )
    video_store, video_id = _store(tmp_path / "video", mode="video")
    video_store.approve_dry_run(video_id, owner_id="owner-1")
    with pytest.raises(MultimediaAudioRegistrationError, match="audio asset"):
        register_multimedia_audio_production(
            video_id,
            request,
            owner_id="owner-1",
            store=video_store,
            playback=_Playback(),  # type: ignore[arg-type]
        )
