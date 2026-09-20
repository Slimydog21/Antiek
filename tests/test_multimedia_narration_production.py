from __future__ import annotations

import hashlib
import wave
from dataclasses import replace
from pathlib import Path

import pytest

import substrate.multimedia.narration_production as production
from substrate.contracts.multimedia import GeneratedFile
from substrate.multimedia.audio_assembly import ChapterAudio
from substrate.multimedia.narration_production import (
    NarrationProductionArtifact,
    NarrationProductionError,
    NarrationProductionManifest,
    NarrationSource,
    produce_narration_track,
)

KEY = b"narration-production-integrity-key"


def _wav(path: Path, duration: float, sample: int) -> None:
    rate = 8_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(sample.to_bytes(2, "little", signed=True) * round(rate * duration))
    path.chmod(0o600)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def authority(tmp_path: Path):
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    _wav(first, 0.4, 100)
    _wav(second, 0.6, 200)
    chapters = tuple(
        ChapterAudio(
            chapter_id=f"chapter-{index}",
            title=f"Chapter {index}",
            sequence=index,
            audio_file_id=f"audio-{index}",
            duration_seconds=duration,
            start_offset_seconds=start,
            script_line_ids=(f"line-{index}",),
            source_chunk_ids=(f"chunk-{index}",),
            paragraph_ids=(f"para-{index}",),
            recap_prompt="Recall the evidence.",
        )
        for index, (duration, start) in enumerate(((0.4, 0.0), (0.6, 0.4)))
    )
    files = tuple(
        GeneratedFile(
            file_id=f"audio-{index}",
            kind="audio",
            storage_uri=f"antiek-mm://asset/revision/audio-{index}.wav",
            sha256=_sha(path),
            mime="audio/wav",
            provider="fixture",
            duration_seconds=duration,
        )
        for index, (path, duration) in enumerate(((first, 0.4), (second, 0.6)))
    )
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    return chapters, files, {"audio-0": str(first), "audio-1": str(second)}, output


def test_produces_and_reopens_ordered_narration(authority) -> None:
    chapters, files, paths, output = authority
    artifact = produce_narration_track(
        asset_id="asset",
        revision_id="revision",
        chapters=chapters,
        generated_files=files,
        chapter_paths=paths,
        output_dir=str(output),
        integrity_key=KEY,
        sample_rate_hz=16_000,
    )
    assert artifact.manifest.duration_seconds == 1.0
    assert tuple(row.audio_file_id for row in artifact.manifest.sources) == ("audio-0", "audio-1")
    reopened = NarrationProductionArtifact.reopen(artifact.to_json(), KEY)
    assert reopened == artifact and Path(artifact.manifest.output_path).is_file()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda paths: {"audio-0": paths["audio-0"]}, "exactly cover"),
        (lambda paths: {**paths, "extra": paths["audio-0"]}, "exactly cover"),
    ],
)
def test_mapping_must_be_exact(authority, mutate, message: str) -> None:
    chapters, files, paths, output = authority
    with pytest.raises(ValueError, match=message):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths=mutate(paths),
            output_dir=str(output),
            integrity_key=KEY,
        )
def test_manifest_digest_tamper_fails_before_process(authority) -> None:
    chapters, files, paths, output = authority
    changed = list(files)
    changed[0] = changed[0].model_copy(update={"sha256": "0" * 64})
    with pytest.raises(NarrationProductionError, match="digest"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=tuple(changed),
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )


def test_symlink_and_public_input_fail(authority, tmp_path: Path) -> None:
    chapters, files, paths, output = authority
    link = tmp_path / "linked.wav"
    link.symlink_to(paths["audio-0"])
    with pytest.raises(NarrationProductionError, match="symlink"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths={**paths, "audio-0": str(link)},
            output_dir=str(output),
            integrity_key=KEY,
        )
    Path(paths["audio-0"]).chmod(0o644)
    with pytest.raises(NarrationProductionError, match="private"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )


def test_reopen_rejects_output_drift(authority) -> None:
    chapters, files, paths, output = authority
    artifact = produce_narration_track(
        asset_id="asset",
        revision_id="revision",
        chapters=chapters,
        generated_files=files,
        chapter_paths=paths,
        output_dir=str(output),
        integrity_key=KEY,
    )
    Path(artifact.manifest.output_path).write_bytes(b"drift")
    Path(artifact.manifest.output_path).chmod(0o600)
    with pytest.raises(NarrationProductionError, match="digest"):
        NarrationProductionArtifact.reopen(artifact.to_json(), KEY)


def test_identifiers_cannot_escape_output_root(authority) -> None:
    chapters, files, paths, output = authority
    with pytest.raises(ValueError, match="asset_id"):
        produce_narration_track(
            asset_id="../escape",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )
    assert not (output.parent / "escape-revision-narration").exists()


def test_duplicate_generated_ids_and_hardlink_aliases_fail(authority, tmp_path: Path) -> None:
    chapters, files, paths, output = authority
    with pytest.raises(ValueError, match="unique"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=(*files, files[0]),
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )
    cross_kind_duplicate = GeneratedFile(
        file_id="audio-0",
        kind="image",
        storage_uri="antiek-mm://asset/revision/image.png",
        sha256="0" * 64,
        mime="image/png",
        provider="fixture",
        width_px=1,
        height_px=1,
    )
    with pytest.raises(ValueError, match="globally unique"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=(*files, cross_kind_duplicate),
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )
    alias = tmp_path / "alias.wav"
    alias.hardlink_to(paths["audio-0"])
    changed = {**paths, "audio-1": str(alias)}
    changed_files = (files[0], files[1].model_copy(update={"sha256": files[0].sha256}))
    with pytest.raises(NarrationProductionError, match="private|alias"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=changed_files,
            chapter_paths=changed,
            output_dir=str(output),
            integrity_key=KEY,
        )


def test_bad_probe_shape_and_post_publication_failure_leave_no_destination(
    authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapters, files, paths, output = authority
    probes = iter(((0.4, "pcm_s16le", 8_000, 1), (0.6, "pcm_s16le", 8_000, 1), (1.0, "aac", 16_000, 1)))
    monkeypatch.setattr(production, "_probe_audio", lambda *_: next(probes))
    with pytest.raises(NarrationProductionError, match="shape"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
            sample_rate_hz=16_000,
        )
    assert not (output / "asset-revision-narration").exists()


def test_post_publication_reopen_failure_rolls_back(
    authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapters, files, paths, output = authority

    def fail_reopen(cls, payload, key):
        raise NarrationProductionError("forced reopen failure")

    monkeypatch.setattr(NarrationProductionArtifact, "reopen", classmethod(fail_reopen))
    with pytest.raises(NarrationProductionError, match="forced"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )
    assert not (output / "asset-revision-narration").exists()


def test_per_chapter_duration_cannot_hide_behind_equal_aggregate(authority) -> None:
    chapters, files, paths, output = authority
    _wav(Path(paths["audio-0"]), 0.449, 100)
    _wav(Path(paths["audio-1"]), 0.551, 200)
    changed_files = tuple(
        row.model_copy(update={"sha256": _sha(Path(paths[row.file_id]))}) for row in files
    )
    with pytest.raises(NarrationProductionError, match="materialized bytes"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=chapters,
            generated_files=changed_files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )


def test_sub_millisecond_sample_residue_normalizes_to_timeline_precision(authority) -> None:
    chapters, files, paths, output = authority
    _wav(Path(paths["audio-0"]), 0.400375, 100)
    changed_files = (
        files[0].model_copy(update={"sha256": _sha(Path(paths["audio-0"]))}),
        files[1],
    )
    artifact = produce_narration_track(
        asset_id="asset",
        revision_id="revision",
        chapters=chapters,
        generated_files=changed_files,
        chapter_paths=paths,
        output_dir=str(output),
        integrity_key=KEY,
    )
    assert artifact.manifest.duration_seconds == 1.0


def test_declared_chapter_boundary_must_match_concatenation(authority) -> None:
    chapters, files, paths, output = authority
    broken = (chapters[0], replace(chapters[1], start_offset_seconds=999.0))
    with pytest.raises(ValueError, match="timeline"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=broken,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )
    near_zero = (replace(chapters[0], start_offset_seconds=0.0005), chapters[1])
    with pytest.raises(ValueError, match="timeline"):
        produce_narration_track(
            asset_id="asset",
            revision_id="revision",
            chapters=near_zero,
            generated_files=files,
            chapter_paths=paths,
            output_dir=str(output),
            integrity_key=KEY,
        )


def test_manifest_duration_must_exactly_equal_source_sum() -> None:
    sources = (
        NarrationSource(
            sequence=0,
            chapter_id="chapter-0",
            audio_file_id="audio-0",
            path="/private/source.wav",
            sha256="0" * 64,
            duration_seconds=1.0,
        ),
    )
    with pytest.raises(ValueError, match="duration"):
        NarrationProductionManifest(
            asset_id="asset",
            revision_id="revision",
            output_path="/private/narration.wav",
            output_sha256="1" * 64,
            duration_seconds=1.049,
            sample_rate_hz=24_000,
            channels=1,
            sources=sources,
        )
    with pytest.raises(ValueError, match="millisecond"):
        NarrationSource(
            sequence=0,
            chapter_id="chapter-0",
            audio_file_id="audio-0",
            path="/private/source.wav",
            sha256="0" * 64,
            duration_seconds=1.0004,
        )
