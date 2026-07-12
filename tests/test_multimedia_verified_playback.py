from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import substrate.multimedia.verified_playback as playback_module
from substrate.multimedia.verified_playback import VerifiedPlaybackError, VerifiedPlaybackRuntime

_KEY = b"k" * 32


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[VerifiedPlaybackRuntime, bytes, bytes]:
    os.chmod(tmp_path, 0o700)
    video = tmp_path / "documentary.mp4"
    audio = tmp_path / "narration.wav"
    video_bytes = b"video-media-authority"
    audio_bytes = b"audio-media-authority"
    video.write_bytes(video_bytes)
    audio.write_bytes(audio_bytes)
    os.chmod(video, 0o600)
    os.chmod(audio, 0o600)
    render_manifest = SimpleNamespace(
        asset_id="mm-1",
        revision_id="rev-1",
        output_path=str(video),
        output_sha256=hashlib.sha256(video_bytes).hexdigest(),
        duration_seconds=12.5,
        width_px=1920,
        height_px=1080,
        chapter_ids=("chapter-1",),
    )
    narration_manifest = SimpleNamespace(
        asset_id="mm-1",
        revision_id="rev-1",
        output_path=str(audio),
        output_sha256=hashlib.sha256(audio_bytes).hexdigest(),
    )
    receipt = SimpleNamespace(
        asset_id="mm-1",
        revision_id="rev-1",
        render=SimpleNamespace(manifest=render_manifest),
        narration=SimpleNamespace(manifest=narration_manifest),
        to_json=lambda: '{"asset_id":"mm-1","revision_id":"rev-1"}',
    )
    monkeypatch.setattr(
        "substrate.multimedia.verified_playback.EducationalVideoReceipt.reopen_from_file",
        lambda *_args: receipt,
    )
    return VerifiedPlaybackRuntime(str(tmp_path), _KEY, _KEY, _KEY, _KEY), video_bytes, audio_bytes


def test_metadata_and_ranges_are_derived_from_reopened_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, video, _audio = _runtime(tmp_path, monkeypatch)
    metadata = runtime.metadata(asset_id="mm-1", revision_id="rev-1")
    assert metadata.video_size_bytes == len(video)
    assert metadata.chapter_ids == ("chapter-1",)

    result = runtime.read(
        asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=2-6"
    )
    assert result.payload == video[2:7]
    assert (result.start, result.end, result.total) == (2, 6, len(video))
    suffix = runtime.read(
        asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=-5"
    )
    assert suffix.payload == video[-5:]
    full = runtime.read(
        asset_id="mm-1", revision_id="rev-1", kind="video", range_header=None
    )
    assert full.payload == video

    monkeypatch.setattr(playback_module, "_MAX_RANGE_BYTES", 4)
    streamed = runtime.read(
        asset_id="mm-1", revision_id="rev-1", kind="video", range_header=None
    )
    assert streamed.payload is None and streamed.stream is not None
    try:
        assert streamed.stream.read() == video
    finally:
        streamed.stream.close()


def test_identity_digest_permissions_and_ranges_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _video, _audio = _runtime(tmp_path, monkeypatch)
    with pytest.raises(VerifiedPlaybackError, match="identity"):
        runtime.metadata(asset_id="mm-1", revision_id="rev-2")

    video_path = tmp_path / "documentary.mp4"
    video_path.write_bytes(b"tampered")
    with pytest.raises(VerifiedPlaybackError, match="digest"):
        runtime.read(asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=0-1")

    video_path.write_bytes(b"video-media-authority")
    os.chmod(video_path, 0o644)
    with pytest.raises(VerifiedPlaybackError, match="private"):
        runtime.read(asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=0-1")

    os.chmod(video_path, 0o600)
    with pytest.raises(VerifiedPlaybackError, match="range"):
        runtime.read(asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=999-1000")


def test_symlinked_media_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _video, _audio = _runtime(tmp_path, monkeypatch)
    video = tmp_path / "documentary.mp4"
    target = tmp_path / "replacement.mp4"
    target.write_bytes(b"video-media-authority")
    os.chmod(target, 0o600)
    video.unlink()
    video.symlink_to(target)
    with pytest.raises(VerifiedPlaybackError, match="unsafe"):
        runtime.read(asset_id="mm-1", revision_id="rev-1", kind="video", range_header="bytes=0-1")
