from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import pytest

from substrate.contracts.multimedia import GeneratedFile
from substrate.multimedia.audio_assembly import ChapterAudio
from substrate.multimedia.educational_video_production import (
    EducationalVideoProductionError,
    produce_educational_video,
)
from substrate.multimedia.narration_production import (
    NarrationProductionError,
    produce_narration_track,
)
from substrate.multimedia.video import TimelineEntry
from substrate.multimedia.visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

NARRATION_KEY = b"narration-production-integrity-key"
VISUAL_KEY = b"visual-packet-integrity-key-32b!"
EVIDENCE_KEY = b"visual-evidence-authority-key-32"
RENDER_KEY = b"render-artifact-integrity-key-32"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id,
        visual_label=selection.visual_label,
        content_sha256=digest,
        evidence_digest="a" * 64,
        authority_key=EVIDENCE_KEY,
    )


@pytest.fixture
def state(tmp_path: Path):
    chapter_path = tmp_path / "chapter.wav"
    with wave.open(str(chapter_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 8_000)
    chapter_path.chmod(0o600)
    chapter = ChapterAudio(
        chapter_id="chapter-1",
        title="Lift",
        sequence=0,
        audio_file_id="audio-1",
        duration_seconds=1.0,
        start_offset_seconds=0.0,
        script_line_ids=("line-1",),
        source_chunk_ids=("chunk-lift",),
        paragraph_ids=("para-1",),
        recap_prompt="Recall lift.",
    )
    generated = GeneratedFile(
        file_id="audio-1",
        kind="audio",
        storage_uri="antiek-mm://asset/revision/audio-1.wav",
        sha256=_sha(chapter_path),
        mime="audio/wav",
        provider="fixture",
        duration_seconds=1.0,
    )
    narration_root = tmp_path / "narration"
    narration_root.mkdir(mode=0o700)
    narration = produce_narration_track(
        asset_id="asset",
        revision_id="revision",
        chapters=(chapter,),
        generated_files=(generated,),
        chapter_paths={"audio-1": str(chapter_path)},
        output_dir=str(narration_root),
        integrity_key=NARRATION_KEY,
    )
    still = tmp_path / "lift.ppm"
    still.write_bytes(b"P6\n16 16\n255\n" + bytes([40, 100, 180]) * 256)
    still.chmod(0o600)
    timeline = (
        TimelineEntry(
            scene_id="scene-1",
            chapter_id="chapter-1",
            start_seconds=0,
            end_seconds=1,
            motion="slow_zoom_in",
            visual_label="diagram",
            caption="Lift follows from pressure differences.",
            source_chunk_ids=("chunk-lift",),
        ),
    )
    selection = ReviewedVisualSelection(
        scene_id="scene-1",
        path=str(still),
        expected_sha256=_sha(still),
        visual_label="diagram",
        source_chunk_ids=("chunk-lift",),
    )
    return narration, timeline, selection, tmp_path


def _produce(state, **changes):
    narration, timeline, selection, root = state
    visual_root, render_root = root / "visuals", root / "renders"
    visual_root.mkdir(mode=0o700, exist_ok=True)
    render_root.mkdir(mode=0o700, exist_ok=True)
    values = dict(
        asset_id="asset",
        revision_id="revision",
        narration=narration,
        narration_integrity_key=NARRATION_KEY,
        timeline=timeline,
        selections=(selection,),
        visual_output_dir=str(visual_root),
        render_output_dir=str(render_root),
        visual_integrity_key=VISUAL_KEY,
        evidence_authority_key=EVIDENCE_KEY,
        render_integrity_key=RENDER_KEY,
        verify_evidence=_evidence,
        width_px=320,
        height_px=240,
        fps=10,
    )
    values.update(changes)
    return produce_educational_video(**values)


def test_real_end_to_end_educational_video(state) -> None:
    result = _produce(state)
    rendered = result.documentary.render_artifact.manifest
    assert rendered.narration_path == result.narration.manifest.output_path
    assert rendered.narration_sha256 == result.narration.manifest.output_sha256
    assert rendered.duration_seconds == 1.0
    assert Path(rendered.output_path).is_file()


def test_wrong_narration_key_fails_before_render(state) -> None:
    with pytest.raises(NarrationProductionError, match="MAC"):
        _produce(state, narration_integrity_key=b"wrong-key-that-is-still-long-enough!")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"asset_id": "other"}, "identity"),
        (
            {
                "timeline": (
                    TimelineEntry(
                        scene_id="scene-1",
                        chapter_id="chapter-1",
                        start_seconds=0,
                        end_seconds=0.5,
                        motion="hold",
                        visual_label="diagram",
                        caption="Short.",
                        source_chunk_ids=("chunk-lift",),
                    ),
                )
            },
            "duration",
        ),
        (
            {
                "timeline": (
                    TimelineEntry(
                        scene_id="scene-1",
                        chapter_id="chapter-other",
                        start_seconds=0,
                        end_seconds=1,
                        motion="hold",
                        visual_label="diagram",
                        caption="Different chapter.",
                        source_chunk_ids=("chunk-lift",),
                    ),
                )
            },
            "chapter boundaries",
        ),
    ],
)
def test_identity_and_duration_drift_fail_before_render(state, changes, message: str) -> None:
    with pytest.raises(EducationalVideoProductionError, match=message):
        _produce(state, **changes)


def test_narration_output_tamper_fails_before_render(state) -> None:
    narration, _, _, _ = state
    path = Path(narration.manifest.output_path)
    path.write_bytes(b"tamper")
    path.chmod(0o600)
    with pytest.raises(NarrationProductionError, match="digest"):
        _produce(state)


def test_multi_chapter_boundary_drift_fails_before_render(tmp_path: Path) -> None:
    chapters = []
    generated_files = []
    chapter_paths = {}
    for sequence in range(2):
        chapter_id = f"chapter-{sequence + 1}"
        audio_file_id = f"audio-{sequence + 1}"
        path = tmp_path / f"{audio_file_id}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8_000)
            output.writeframes(b"\x00\x00" * 8_000)
        path.chmod(0o600)
        chapters.append(
            ChapterAudio(
                chapter_id=chapter_id,
                title=chapter_id,
                sequence=sequence,
                audio_file_id=audio_file_id,
                duration_seconds=1.0,
                start_offset_seconds=float(sequence),
                script_line_ids=(f"line-{sequence}",),
                source_chunk_ids=(f"chunk-{sequence}",),
                paragraph_ids=(f"para-{sequence}",),
                recap_prompt=f"Recall {chapter_id}.",
            )
        )
        generated_files.append(
            GeneratedFile(
                file_id=audio_file_id,
                kind="audio",
                storage_uri=f"antiek-mm://asset/revision/{audio_file_id}.wav",
                sha256=_sha(path),
                mime="audio/wav",
                provider="fixture",
                duration_seconds=1.0,
            )
        )
        chapter_paths[audio_file_id] = str(path)

    narration_root = tmp_path / "narration"
    narration_root.mkdir(mode=0o700)
    narration = produce_narration_track(
        asset_id="asset",
        revision_id="revision",
        chapters=tuple(chapters),
        generated_files=tuple(generated_files),
        chapter_paths=chapter_paths,
        output_dir=str(narration_root),
        integrity_key=NARRATION_KEY,
    )
    drifted_timeline = (
        TimelineEntry(
            scene_id="scene-1",
            chapter_id="chapter-1",
            start_seconds=0,
            end_seconds=1.5,
            motion="hold",
            visual_label="diagram",
            caption="Late boundary.",
        ),
        TimelineEntry(
            scene_id="scene-2",
            chapter_id="chapter-2",
            start_seconds=1.5,
            end_seconds=2,
            motion="hold",
            visual_label="diagram",
            caption="Compressed boundary.",
        ),
    )
    visual_root = tmp_path / "visuals"
    render_root = tmp_path / "renders"

    with pytest.raises(EducationalVideoProductionError, match="chapter boundaries"):
        produce_educational_video(
            asset_id="asset",
            revision_id="revision",
            narration=narration,
            narration_integrity_key=NARRATION_KEY,
            timeline=drifted_timeline,
            selections=(),
            visual_output_dir=str(visual_root),
            render_output_dir=str(render_root),
            visual_integrity_key=VISUAL_KEY,
            evidence_authority_key=EVIDENCE_KEY,
            render_integrity_key=RENDER_KEY,
            verify_evidence=_evidence,
        )
    assert not visual_root.exists()
    assert not render_root.exists()
