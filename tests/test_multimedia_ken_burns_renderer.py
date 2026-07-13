from __future__ import annotations

import ast
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

import substrate.multimedia.ken_burns_renderer as renderer
from substrate.multimedia.ken_burns_renderer import (
    KenBurnsRenderArtifact,
    KenBurnsRenderError,
    KenBurnsRenderManifest,
    SceneStillInput,
)
from substrate.multimedia.ken_burns_renderer import (
    render_ken_burns_documentary as _render_ken_burns_documentary,
)
from substrate.multimedia.media_executables import DEFAULT_FFMPEG_PATH
from substrate.multimedia.video import TimelineEntry

_INTEGRITY_KEY = b"antiek-render-test-key-32-bytes!!"


def render_ken_burns_documentary(**kwargs):
    return _render_ken_burns_documentary(integrity_key=_INTEGRITY_KEY, **kwargs)


def _ppm(path: Path, rgb: tuple[int, int, int]) -> None:
    width, height = 96, 54
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode() + bytes(rgb) * width * height)


def _wav(path: Path, duration: float) -> None:
    rate = 16_000
    frames = round(rate * duration)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        samples = bytearray()
        for index in range(frames):
            sample = int(500 * math.sin(2 * math.pi * 220 * index / rate))
            samples.extend(sample.to_bytes(2, "little", signed=True))
        output.writeframes(bytes(samples))


def _timeline() -> tuple[TimelineEntry, ...]:
    return (
        TimelineEntry(
            scene_id="scene-intro",
            chapter_id="intro",
            start_seconds=0,
            end_seconds=0.6,
            motion="slow_zoom_in",
            visual_label="generated",
            caption="The first sourced explanation.",
            source_chunk_ids=("chunk-1",),
        ),
        TimelineEntry(
            scene_id="scene-history",
            chapter_id="history",
            start_seconds=0.6,
            end_seconds=1.2,
            motion="pan_right",
            visual_label="sourced",
            caption="The second sourced explanation.",
            source_chunk_ids=("chunk-2",),
        ),
    )


def _inputs(first: Path, second: Path) -> tuple[SceneStillInput, ...]:
    return (
        SceneStillInput(
            scene_id="scene-intro",
            path=str(first),
            visual_label="generated",
            source_chunk_ids=("chunk-1",),
        ),
        SceneStillInput(
            scene_id="scene-history",
            path=str(second),
            visual_label="sourced",
            source_chunk_ids=("chunk-2",),
        ),
    )


@pytest.fixture
def media(tmp_path: Path):
    first = tmp_path / "first.ppm"
    second = tmp_path / "second.ppm"
    narration = tmp_path / "narration.wav"
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    _ppm(first, (220, 30, 30))
    _ppm(second, (30, 80, 220))
    _wav(narration, 1.2)
    return first, second, narration, output


def test_real_ffmpeg_render_has_verified_streams_and_reopens_without_process(
    media, monkeypatch
) -> None:
    first, second, narration, output = media
    artifact = render_ken_burns_documentary(
        asset_id="aircraft",
        revision_id="revision-1",
        timeline=_timeline(),
        stills=_inputs(first, second),
        narration_path=str(narration),
        output_dir=str(output),
        width_px=320,
        height_px=180,
        fps=12,
    )
    manifest = artifact.manifest
    assert Path(manifest.output_path).read_bytes()[4:8] == b"ftyp"
    assert (manifest.video_codec, manifest.audio_codec, manifest.subtitle_codec) == (
        "h264",
        "aac",
        "mov_text",
    )
    assert (manifest.width_px, manifest.height_px) == (320, 180)
    assert manifest.scene_ids == ("scene-intro", "scene-history")
    assert manifest.visual_labels == ("generated", "sourced")
    assert all(cue.source_chunk_ids for cue in manifest.captions)
    sidecar = output / "aircraft-revision-1" / "render.json"
    assert sidecar.exists()
    frame = output / "decoded-frame.png"
    subprocess.run(
        [
            DEFAULT_FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
            "-ss", "0.2", "-i", manifest.output_path, "-frames:v", "1", str(frame),
        ],
        check=True,
    )
    with Image.open(frame) as decoded:
        right_edge = decoded.convert("RGB").getpixel((decoded.width - 4, decoded.height // 2))
    assert right_edge[0] > 150 and right_edge[1] < 100 and right_edge[2] < 100

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("no subprocess"))
    assert KenBurnsRenderArtifact.reopen(sidecar.read_text(), _INTEGRITY_KEY) == artifact


def test_reopen_detects_output_caption_narration_and_input_drift(media) -> None:
    first, second, narration, output = media
    artifact = render_ken_burns_documentary(
        asset_id="drift",
        revision_id="revision-1",
        timeline=_timeline(),
        stills=_inputs(first, second),
        narration_path=str(narration),
        output_dir=str(output),
        width_px=320,
        height_px=180,
        fps=10,
    )
    payload = artifact.to_json()
    for path in (
        Path(artifact.manifest.output_path),
        Path(artifact.manifest.captions_path),
        narration,
        first,
    ):
        original = path.read_bytes()
        path.write_bytes(original + b"tamper")
        with pytest.raises(KenBurnsRenderError, match="digest"):
            KenBurnsRenderArtifact.reopen(payload, _INTEGRITY_KEY)
        path.write_bytes(original)


def test_timeline_still_authority_and_private_output_fail_closed(media) -> None:
    first, second, narration, output = media
    rows = list(_inputs(first, second))
    rows[0] = rows[0].model_copy(update={"visual_label": "archival"})
    with pytest.raises(ValueError, match="disclosure"):
        render_ken_burns_documentary(
            asset_id="bad",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=tuple(rows),
            narration_path=str(narration),
            output_dir=str(output),
        )
    output.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        render_ken_burns_documentary(
            asset_id="bad",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )


def test_symlink_input_existing_destination_and_timeout_fail_closed(media, monkeypatch) -> None:
    first, second, narration, output = media
    link = first.parent / "link.ppm"
    link.symlink_to(first)
    rows = list(_inputs(first, second))
    rows[0] = rows[0].model_copy(update={"path": str(link)})
    with pytest.raises(KenBurnsRenderError, match="unavailable"):
        render_ken_burns_documentary(
            asset_id="symlink",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=tuple(rows),
            narration_path=str(narration),
            output_dir=str(output),
        )
    (output / "exists-revision-1").mkdir()
    with pytest.raises(FileExistsError):
        render_ken_burns_documentary(
            asset_id="exists",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(KenBurnsRenderError, match="command failed"):
        render_ken_burns_documentary(
            asset_id="timeout",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )


def test_motion_filters_and_ffmpeg_argv_are_fixed_and_network_free(media) -> None:
    first, second, narration, output = media
    filters = {
        motion: renderer._motion_filter(motion, 30)
        for motion in (
            "pan_left",
            "pan_right",
            "slow_zoom_in",
            "slow_zoom_out",
            "hold",
            "map_callout",
        )
    }
    assert len(set(filters.values())) == 6
    argv = renderer._ffmpeg_argv(
        ffmpeg=str(Path(shutil.which("ffmpeg") or "").resolve()),
        audio_format="wav",
        timeline=_timeline(),
        still_paths=(first, second),
        narration_path=narration,
        captions_path=first.parent / "captions.vtt",
        output_path=output / "out.mp4",
        width_px=320,
        height_px=180,
        fps=12,
    )
    assert argv[0].endswith("/ffmpeg") and "-nostdin" in argv
    assert argv.count("-protocol_whitelist") == 4
    assert "-fs" in argv
    assert not any("http://" in item or "https://" in item for item in argv)
    tree = ast.parse(Path("substrate/multimedia/ken_burns_renderer.py").read_text())
    assert not any(
        isinstance(node, ast.keyword)
        and node.arg == "shell"
        and not isinstance(node.value, ast.Constant)
        for node in ast.walk(tree)
    )


def test_manifest_revalidates_nested_construct_and_digest_tamper(media) -> None:
    first, second, narration, output = media
    artifact = render_ken_burns_documentary(
        asset_id="manifest",
        revision_id="revision-1",
        timeline=_timeline(),
        stills=_inputs(first, second),
        narration_path=str(narration),
        output_dir=str(output),
        width_px=320,
        height_px=180,
        fps=10,
    )
    row = artifact.manifest.inputs[0].model_construct(
        **{**artifact.manifest.inputs[0].model_dump(), "scene_id": "ghost"}
    )
    forged = KenBurnsRenderManifest.model_construct(
        **{
            **artifact.manifest.model_dump(mode="python"),
            "inputs": (row, *artifact.manifest.inputs[1:]),
        }
    )
    with pytest.raises(ValidationError, match="scene order"):
        KenBurnsRenderArtifact.seal(forged, _INTEGRITY_KEY)
    payload = json.loads(artifact.to_json())
    payload["manifest"]["revision_id"] = "forged"
    with pytest.raises(KenBurnsRenderError, match="digest"):
        KenBurnsRenderArtifact.reopen(json.dumps(payload), _INTEGRITY_KEY)
    forged_manifest = KenBurnsRenderManifest.model_validate(payload["manifest"])
    payload["manifest_sha256"] = renderer._manifest_digest(
        forged_manifest, b"attacker-controlled-key-32-bytes"
    )
    with pytest.raises(KenBurnsRenderError, match="digest"):
        KenBurnsRenderArtifact.reopen(json.dumps(payload), _INTEGRITY_KEY)


def test_identifiers_passive_formats_hardlinks_and_executables_are_bounded(media) -> None:
    first, second, narration, output = media
    for asset_id in ("../escape", "/absolute", "bad/name"):
        with pytest.raises(ValueError, match="asset_id"):
            render_ken_burns_documentary(
                asset_id=asset_id,
                revision_id="revision-1",
                timeline=_timeline(),
                stills=_inputs(first, second),
                narration_path=str(narration),
                output_dir=str(output),
            )
    playlist = first.parent / "active.m3u8"
    playlist.write_text("https://example.invalid/remote.png")
    rows = list(_inputs(first, second))
    rows[0] = rows[0].model_copy(update={"path": str(playlist)})
    with pytest.raises(ValueError, match="format"):
        render_ken_burns_documentary(
            asset_id="playlist",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=tuple(rows),
            narration_path=str(narration),
            output_dir=str(output),
        )
    hardlink = first.parent / "hardlink.ppm"
    hardlink.hardlink_to(first)
    rows[0] = rows[0].model_copy(update={"path": str(hardlink)})
    with pytest.raises(KenBurnsRenderError, match="regular file"):
        render_ken_burns_documentary(
            asset_id="hardlink",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=tuple(rows),
            narration_path=str(narration),
            output_dir=str(output),
        )
    fake = first.parent / "ffmpeg"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o700)
    with pytest.raises(ValueError, match="approved"):
        render_ken_burns_documentary(
            asset_id="fake-exec",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
            ffmpeg_path=str(fake),
        )


def test_narration_duration_and_atomic_bundle_publication_fail_closed(media, monkeypatch) -> None:
    first, second, narration, output = media
    _wav(narration, 0.4)
    with pytest.raises(KenBurnsRenderError, match="narration duration"):
        render_ken_burns_documentary(
            asset_id="short-audio",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )
    _wav(narration, 1.2)
    real_rename = renderer.os.rename

    def fail_publish(source, destination, **kwargs):
        if str(destination).endswith("atomic-revision-1"):
            raise OSError("publication crash")
        return real_rename(source, destination, **kwargs)

    monkeypatch.setattr(renderer.os, "rename", fail_publish)
    with pytest.raises(OSError, match="publication crash"):
        render_ken_burns_documentary(
            asset_id="atomic",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
            width_px=320,
            height_px=180,
            fps=10,
        )
    assert not (output / "atomic-revision-1").exists()


def test_manifest_media_and_probe_resource_ceilings_fail_closed(media, monkeypatch) -> None:
    first, second, narration, output = media
    with pytest.raises(KenBurnsRenderError, match="manifest exceeds"):
        KenBurnsRenderArtifact.reopen(b" " * (renderer._MAX_MANIFEST_BYTES + 1), _INTEGRITY_KEY)

    monkeypatch.setattr(renderer, "_MAX_TOTAL_STILL_BYTES", first.stat().st_size)
    with pytest.raises(KenBurnsRenderError, match="aggregate"):
        render_ken_burns_documentary(
            asset_id="aggregate",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )
    monkeypatch.setattr(renderer, "_MAX_TOTAL_STILL_BYTES", 512 * 1024 * 1024)
    monkeypatch.setattr(renderer, "_MAX_TOTAL_IMAGE_PIXELS", 96 * 54)
    with pytest.raises(KenBurnsRenderError, match="aggregate pixel"):
        render_ken_burns_documentary(
            asset_id="aggregate-pixels",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )
    monkeypatch.setattr(renderer, "_MAX_TOTAL_IMAGE_PIXELS", 120_000_000)
    first.write_bytes(b"P6\n100000 100000\n255\n")
    with pytest.raises(KenBurnsRenderError, match="pixel ceiling"):
        render_ken_burns_documentary(
            asset_id="pixel-bomb",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )

    def excessive_output(argv, **kwargs):
        kwargs["stdout"].write(b"x" * (renderer._MAX_COMMAND_OUTPUT_BYTES + 1))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", excessive_output)
    executable, descriptor = renderer._open_executable(
        str(Path(shutil.which("ffprobe") or "").resolve()), "ffprobe"
    )
    try:
        with pytest.raises(KenBurnsRenderError, match="output exceeded"):
            renderer._run([executable], 1, executable_fd=descriptor, capture=True)
    finally:
        renderer.os.close(descriptor)


def test_staging_allocation_failure_closes_pinned_descriptors(media, monkeypatch) -> None:
    first, second, narration, output = media
    descriptors = [renderer.os.open("/dev/null", renderer.os.O_RDONLY) for _ in range(3)]
    monkeypatch.setattr(renderer, "_private_output_dir", lambda value: (output, descriptors[0]))
    paths = iter(
        (
            "/opt/homebrew/Cellar/ffmpeg/8.1.1/bin/ffmpeg",
            "/opt/homebrew/Cellar/ffmpeg/8.1.1/bin/ffprobe",
        )
    )
    fds = iter(descriptors[1:])
    monkeypatch.setattr(renderer, "_open_executable", lambda value, name: (next(paths), next(fds)))

    def fail_staging(**kwargs):
        raise OSError("no staging capacity")

    monkeypatch.setattr(renderer.tempfile, "TemporaryDirectory", fail_staging)
    with pytest.raises(OSError, match="staging capacity"):
        render_ken_burns_documentary(
            asset_id="allocation-failure",
            revision_id="revision-1",
            timeline=_timeline(),
            stills=_inputs(first, second),
            narration_path=str(narration),
            output_dir=str(output),
        )
    for descriptor in descriptors:
        with pytest.raises(OSError):
            renderer.os.fstat(descriptor)
