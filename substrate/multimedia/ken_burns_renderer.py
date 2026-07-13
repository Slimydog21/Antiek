"""Local, bounded FFmpeg rendering for accepted Ken Burns timelines."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .video import MotionPreset, TimelineEntry, VisualLabel

_MAX_SCENES = 64
_MAX_STILL_BYTES = 100 * 1024 * 1024
_MAX_TOTAL_STILL_BYTES = 512 * 1024 * 1024
_MAX_IMAGE_PIXELS = 12_000_000
_MAX_TOTAL_IMAGE_PIXELS = 120_000_000
_MAX_AUDIO_BYTES = 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 5 * 1024 * 1024
_MAX_COMMAND_OUTPUT_BYTES = 1024 * 1024
_MAX_DURATION_SECONDS = 45 * 60
_COPY_CHUNK = 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_STILL_FORMATS = {".png": "image2", ".jpg": "image2", ".jpeg": "image2", ".ppm": "image2"}
_AUDIO_FORMATS = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "mov",
    ".aac": "aac",
    ".flac": "flac",
    ".ogg": "ogg",
}
_APPROVED_EXECUTABLE_ROOTS = (Path("/opt/homebrew/Cellar/ffmpeg"), Path("/usr/bin"))
_MIN_INTEGRITY_KEY_BYTES = 32


class KenBurnsRenderError(RuntimeError):
    """A local render or its verification failed closed."""


class _RenderModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class SceneStillInput(_RenderModel):
    scene_id: str
    path: str
    visual_label: VisualLabel
    source_chunk_ids: tuple[str, ...] = ()


class RenderedInput(_RenderModel):
    scene_id: str
    path: str
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    visual_label: VisualLabel
    source_chunk_ids: tuple[str, ...] = ()


class RenderedCaption(_RenderModel):
    cue_id: str
    scene_id: str
    chapter_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)
    source_chunk_ids: tuple[str, ...] = ()


class KenBurnsRenderManifest(_RenderModel):
    schema_version: Literal["antiek.ken-burns-render.v1"] = "antiek.ken-burns-render.v1"
    asset_id: str
    revision_id: str
    output_path: str
    output_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    captions_path: str
    captions_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    narration_path: str
    narration_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    timeline_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    width_px: int = Field(ge=16, le=3840)
    height_px: int = Field(ge=16, le=2160)
    fps: int = Field(ge=1, le=60)
    duration_seconds: float = Field(gt=0, le=_MAX_DURATION_SECONDS)
    video_codec: str
    audio_codec: str
    subtitle_codec: str
    scene_ids: tuple[str, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    chapter_ids: tuple[str, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    motions: tuple[MotionPreset, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    visual_labels: tuple[VisualLabel, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    inputs: tuple[RenderedInput, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    captions: tuple[RenderedCaption, ...] = Field(min_length=1, max_length=_MAX_SCENES)

    @model_validator(mode="after")
    def references_are_complete(self) -> KenBurnsRenderManifest:
        _unique(self.scene_ids, "scene ids")
        _unique((row.scene_id for row in self.inputs), "input scene ids")
        _unique((row.scene_id for row in self.captions), "caption scene ids")
        if tuple(row.scene_id for row in self.inputs) != self.scene_ids:
            raise ValueError("render inputs do not match scene order")
        if tuple(row.scene_id for row in self.captions) != self.scene_ids:
            raise ValueError("render captions do not match scene order")
        if tuple(row.chapter_id for row in self.captions) != self.chapter_ids:
            raise ValueError("render chapters do not match caption order")
        if len(self.motions) != len(self.scene_ids):
            raise ValueError("render motions do not match scene order")
        if tuple(row.visual_label for row in self.inputs) != self.visual_labels:
            raise ValueError("render visual labels drifted from inputs")
        if tuple(row.source_chunk_ids for row in self.inputs) != tuple(
            row.source_chunk_ids for row in self.captions
        ):
            raise ValueError("render source authority drifted between inputs and captions")
        expected = 0.0
        for cue in self.captions:
            if abs(cue.start_seconds - expected) > 0.001:
                raise ValueError("render caption timeline has a gap or overlap")
            expected = cue.end_seconds
        if abs(expected - self.duration_seconds) > 0.05:
            raise ValueError("render captions do not cover the output duration")
        return self


class KenBurnsRenderArtifact(_RenderModel):
    manifest: KenBurnsRenderManifest
    manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @classmethod
    def seal(cls, manifest: KenBurnsRenderManifest, integrity_key: bytes) -> KenBurnsRenderArtifact:
        validated = KenBurnsRenderManifest.model_validate(dict(manifest.__dict__))
        return cls(
            manifest=validated,
            manifest_sha256=_manifest_digest(validated, _integrity_key(integrity_key)),
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(cls, payload: str | bytes, integrity_key: bytes) -> KenBurnsRenderArtifact:
        payload_size = len(payload.encode("utf-8")) if isinstance(payload, str) else len(payload)
        if payload_size > _MAX_MANIFEST_BYTES:
            raise KenBurnsRenderError("render manifest exceeds its byte ceiling")
        artifact = cls.model_validate_json(payload)
        expected = _manifest_digest(artifact.manifest, _integrity_key(integrity_key))
        if not hmac.compare_digest(artifact.manifest_sha256, expected):
            raise KenBurnsRenderError("render manifest digest mismatch")
        manifest = artifact.manifest
        _verify_file_digest(manifest.output_path, manifest.output_sha256, _MAX_AUDIO_BYTES)
        _verify_file_digest(manifest.captions_path, manifest.captions_sha256, _MAX_STILL_BYTES)
        _verify_file_digest(manifest.narration_path, manifest.narration_sha256, _MAX_AUDIO_BYTES)
        for row in manifest.inputs:
            _verify_file_digest(row.path, row.sha256, _MAX_STILL_BYTES)
        return artifact


def render_ken_burns_documentary(
    *,
    asset_id: str,
    revision_id: str,
    timeline: tuple[TimelineEntry, ...],
    stills: tuple[SceneStillInput, ...],
    narration_path: str,
    output_dir: str,
    integrity_key: bytes,
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    width_px: int = 1280,
    height_px: int = 720,
    fps: int = 30,
    timeout_seconds: int = 300,
) -> KenBurnsRenderArtifact:
    """Render under one OS user and publish an HMAC-authorized media bundle.

    The caller owns the integrity key. The trusted local FFmpeg installation and
    same-UID processes are inside this process boundary; untrusted media inputs,
    identifiers, manifests, and other OS users are outside it.
    """
    asset_id = _identifier("asset_id", asset_id)
    revision_id = _identifier("revision_id", revision_id)
    integrity_key = _integrity_key(integrity_key)
    _validate_dimensions(width_px, height_px, fps, timeout_seconds)
    _validate_timeline_inputs(timeline, stills)
    duration = timeline[-1].end_seconds
    if duration <= 0 or duration > _MAX_DURATION_SECONDS:
        raise ValueError("timeline duration is outside the local render boundary")
    output_root, output_root_fd = _private_output_dir(output_dir)
    try:
        ffmpeg, ffmpeg_fd = _open_executable(ffmpeg_path, "ffmpeg")
    except Exception:
        os.close(output_root_fd)
        raise
    try:
        ffprobe, ffprobe_fd = _open_executable(ffprobe_path, "ffprobe")
    except Exception:
        os.close(ffmpeg_fd)
        os.close(output_root_fd)
        raise
    bundle_path = output_root / f"{asset_id}-{revision_id}"
    if bundle_path.exists() or bundle_path.is_symlink():
        os.close(ffmpeg_fd)
        os.close(ffprobe_fd)
        os.close(output_root_fd)
        raise FileExistsError(f"render destination already exists: {bundle_path.name}")
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        temporary = tempfile.TemporaryDirectory(prefix=".ken-burns-", dir=output_root)
        staging_name = temporary.name
        staging = Path(staging_name)
        os.chmod(staging, 0o700)
        output_path = bundle_path / "documentary.mp4"
        captions_path = bundle_path / "captions.vtt"
        staged_inputs: list[tuple[SceneStillInput, Path, str]] = []
        total_still_bytes = 0
        total_image_pixels = 0
        for index, row in enumerate(stills):
            suffix = _passive_suffix(row.path, _STILL_FORMATS, "still")
            staged = staging / f"still-{index:04d}{suffix}"
            digest, copied_bytes = _copy_regular_file(row.path, staged, _MAX_STILL_BYTES)
            total_still_bytes += copied_bytes
            if total_still_bytes > _MAX_TOTAL_STILL_BYTES:
                raise KenBurnsRenderError("still inputs exceed their aggregate byte ceiling")
            total_image_pixels += _validate_image_dimensions(staged, suffix)
            if total_image_pixels > _MAX_TOTAL_IMAGE_PIXELS:
                raise KenBurnsRenderError("still inputs exceed their aggregate pixel ceiling")
            staged_inputs.append((row, staged, digest))
        audio_suffix = _passive_suffix(narration_path, _AUDIO_FORMATS, "narration")
        staged_audio = staging / f"narration{audio_suffix}"
        narration_sha, _ = _copy_regular_file(narration_path, staged_audio, _MAX_AUDIO_BYTES)
        narration_duration = _probe_duration(
            ffprobe,
            ffprobe_fd,
            staged_audio,
            _AUDIO_FORMATS[audio_suffix],
            timeout_seconds,
        )
        if abs(narration_duration - duration) > 0.05:
            raise KenBurnsRenderError("narration duration does not match the timeline")
        staged_captions = staging / "captions.vtt"
        captions = _caption_rows(timeline)
        _write_private_file(staged_captions, _webvtt(captions).encode("utf-8"))
        staged_output = staging / "documentary.mp4"
        argv = _ffmpeg_argv(
            ffmpeg=ffmpeg,
            audio_format=_AUDIO_FORMATS[audio_suffix],
            timeline=timeline,
            still_paths=tuple(row[1] for row in staged_inputs),
            narration_path=staged_audio,
            captions_path=staged_captions,
            output_path=staged_output,
            width_px=width_px,
            height_px=height_px,
            fps=fps,
        )
        _run(argv, timeout_seconds, executable_fd=ffmpeg_fd, capture=False)
        probe = _probe(ffprobe, ffprobe_fd, staged_output, timeout_seconds)
        _verify_probe(probe, width_px, height_px, duration)
        os.chmod(staged_output, 0o600)
        output_sha = _hash_file(staged_output, _MAX_AUDIO_BYTES)
        captions_sha = _hash_file(staged_captions, _MAX_STILL_BYTES)
        _fsync_file(staged_output)
        _fsync_file(staged_captions)
        rendered_inputs = tuple(
            RenderedInput(
                scene_id=row.scene_id,
                path=str(Path(row.path).resolve()),
                sha256=digest,
                visual_label=row.visual_label,
                source_chunk_ids=row.source_chunk_ids,
            )
            for row, _, digest in staged_inputs
        )
        manifest = KenBurnsRenderManifest(
            asset_id=asset_id,
            revision_id=revision_id,
            output_path=str(output_path),
            output_sha256=output_sha,
            captions_path=str(captions_path),
            captions_sha256=captions_sha,
            narration_path=str(Path(narration_path).resolve()),
            narration_sha256=narration_sha,
            timeline_sha256=_timeline_digest(timeline),
            width_px=width_px,
            height_px=height_px,
            fps=fps,
            duration_seconds=round(duration, 3),
            video_codec=str(probe["video_codec"]),
            audio_codec=str(probe["audio_codec"]),
            subtitle_codec=str(probe["subtitle_codec"]),
            scene_ids=tuple(entry.scene_id for entry in timeline),
            chapter_ids=tuple(entry.chapter_id for entry in timeline),
            motions=tuple(entry.motion for entry in timeline),
            visual_labels=tuple(row.visual_label for row in stills),
            inputs=rendered_inputs,
            captions=captions,
        )
        artifact = KenBurnsRenderArtifact.seal(manifest, integrity_key)
        staged_artifact = staging / "render.json"
        _write_private_file(staged_artifact, artifact.to_json().encode("utf-8"))
        for _, staged_path, _ in staged_inputs:
            staged_path.unlink()
        staged_audio.unlink()
        _fsync_dir(staging)
        _verify_directory_identity(output_root, output_root_fd)
        os.rename(
            staging.name, bundle_path.name, src_dir_fd=output_root_fd, dst_dir_fd=output_root_fd
        )
        _fsync_dir(output_root)
        temporary.cleanup()
        return artifact
    finally:
        os.close(ffmpeg_fd)
        os.close(ffprobe_fd)
        os.close(output_root_fd)
        if temporary is not None:
            temporary.cleanup()


def _validate_timeline_inputs(
    timeline: tuple[TimelineEntry, ...], stills: tuple[SceneStillInput, ...]
) -> None:
    if not timeline or len(timeline) > _MAX_SCENES or len(stills) != len(timeline):
        raise ValueError("timeline and still inputs must have one through 64 rows")
    _unique((entry.scene_id for entry in timeline), "timeline scene ids")
    expected = 0.0
    for entry, still in zip(timeline, stills, strict=True):
        if entry.scene_id != still.scene_id:
            raise ValueError("still input does not match timeline scene order")
        if entry.visual_label != still.visual_label:
            raise ValueError("still disclosure label conflicts with timeline")
        if entry.source_chunk_ids != still.source_chunk_ids:
            raise ValueError("still source authority conflicts with timeline")
        if entry.start_seconds < 0 or entry.end_seconds <= entry.start_seconds:
            raise ValueError("timeline entries require positive windows")
        if abs(entry.start_seconds - expected) > 0.001:
            raise ValueError("timeline has a gap or overlap")
        expected = entry.end_seconds


def _caption_rows(timeline: tuple[TimelineEntry, ...]) -> tuple[RenderedCaption, ...]:
    return tuple(
        RenderedCaption(
            cue_id=f"cue-{index:04d}",
            scene_id=entry.scene_id,
            chapter_id=entry.chapter_id,
            start_seconds=entry.start_seconds,
            end_seconds=entry.end_seconds,
            text=entry.caption,
            source_chunk_ids=entry.source_chunk_ids,
        )
        for index, entry in enumerate(timeline)
    )


def _webvtt(captions: tuple[RenderedCaption, ...]) -> str:
    blocks = ["WEBVTT", ""]
    for cue in captions:
        text = cue.text.replace("\r", " ").replace("\n", " ").strip()
        if "-->" in text or not text:
            raise ValueError("caption text is not WebVTT safe")
        blocks.extend(
            [
                cue.cue_id,
                f"{_vtt_time(cue.start_seconds)} --> {_vtt_time(cue.end_seconds)}",
                text,
                "",
            ]
        )
    return "\n".join(blocks)


def _vtt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _ffmpeg_argv(
    *,
    ffmpeg: str,
    audio_format: str,
    timeline: tuple[TimelineEntry, ...],
    still_paths: tuple[Path, ...],
    narration_path: Path,
    captions_path: Path,
    output_path: Path,
    width_px: int,
    height_px: int,
    fps: int,
) -> list[str]:
    argv = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for entry, path in zip(timeline, still_paths, strict=True):
        argv.extend(
            [
                "-protocol_whitelist",
                "file,pipe",
                "-loop",
                "1",
                "-t",
                f"{entry.end_seconds - entry.start_seconds:.3f}",
                "-i",
                str(path),
            ]
        )
    audio_index = len(still_paths)
    subtitle_index = audio_index + 1
    argv.extend(
        [
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            audio_format,
            "-i",
            str(narration_path),
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            "webvtt",
            "-i",
            str(captions_path),
        ]
    )
    filters: list[str] = []
    for index, entry in enumerate(timeline):
        frames = max(1, round((entry.end_seconds - entry.start_seconds) * fps))
        motion = _motion_filter(entry.motion, frames)
        filters.append(
            f"[{index}:v]scale={width_px}:{height_px}:force_original_aspect_ratio=increase,"
            f"crop={width_px}:{height_px},setsar=1,"
            f"zoompan={motion}:d={frames}:s={width_px}x{height_px}:fps={fps},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
    joined = "".join(f"[v{index}]" for index in range(len(timeline)))
    filters.append(f"{joined}concat=n={len(timeline)}:v=1:a=0[vout]")
    argv.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            f"{audio_index}:a:0",
            "-map",
            f"{subtitle_index}:s:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-movflags",
            "+faststart",
            "-fs",
            str(_MAX_AUDIO_BYTES),
            "-t",
            f"{timeline[-1].end_seconds:.3f}",
            str(output_path),
        ]
    )
    return argv


def _motion_filter(motion: MotionPreset, frames: int) -> str:
    if motion == "slow_zoom_in":
        return "z='min(zoom+0.001,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if motion == "slow_zoom_out":
        return "z='if(eq(on,1),1.08,max(zoom-0.001,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if motion == "pan_left":
        return f"z='1.08':x='(iw-iw/zoom)*(1-on/{max(1, frames - 1)})':y='ih/2-(ih/zoom/2)'"
    if motion == "pan_right":
        return f"z='1.08':x='(iw-iw/zoom)*(on/{max(1, frames - 1)})':y='ih/2-(ih/zoom/2)'"
    if motion == "hold":
        return "z='1.0':x='0':y='0'"
    if motion == "map_callout":
        return "z='1.02':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    raise ValueError("unsupported Ken Burns motion preset")


def _probe(ffprobe: str, ffprobe_fd: int, output: Path, timeout: int) -> dict[str, object]:
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,duration,start_time:format=duration",
            "-of",
            "json",
            str(output),
        ],
        timeout,
        executable_fd=ffprobe_fd,
        capture=True,
    )
    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        video = next(row for row in streams if row["codec_type"] == "video")
        audio = next(row for row in streams if row["codec_type"] == "audio")
        subtitle = next(row for row in streams if row["codec_type"] == "subtitle")
        return {
            "width": int(video["width"]),
            "height": int(video["height"]),
            "duration": float(payload["format"]["duration"]),
            "video_codec": video["codec_name"],
            "audio_codec": audio["codec_name"],
            "subtitle_codec": subtitle["codec_name"],
            "video_duration": float(video["duration"]),
            "audio_duration": float(audio["duration"]),
            "subtitle_duration": float(subtitle["duration"]),
            "audio_start": float(audio.get("start_time", 0)),
        }
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise KenBurnsRenderError("ffprobe returned an invalid media shape") from exc


def _verify_probe(probe: dict[str, object], width: int, height: int, duration: float) -> None:
    if probe["width"] != width or probe["height"] != height:
        raise KenBurnsRenderError("render dimensions do not match the request")
    observed_duration = probe["duration"]
    if not isinstance(observed_duration, (int, float)) or (
        abs(float(observed_duration) - duration) > 0.1
    ):
        raise KenBurnsRenderError("render duration does not match the timeline")
    if (probe["video_codec"], probe["audio_codec"], probe["subtitle_codec"]) != (
        "h264",
        "aac",
        "mov_text",
    ):
        raise KenBurnsRenderError("render codecs do not match the fixed contract")
    for name in ("video_duration", "audio_duration", "subtitle_duration"):
        value = probe[name]
        if not isinstance(value, (int, float)) or abs(float(value) - duration) > 0.1:
            raise KenBurnsRenderError("render stream duration does not match the timeline")
    audio_start = probe["audio_start"]
    if not isinstance(audio_start, (int, float)) or abs(float(audio_start)) > 0.05:
        raise KenBurnsRenderError("render narration does not start at zero")


def _probe_duration(
    ffprobe: str,
    ffprobe_fd: int,
    path: Path,
    audio_format: str,
    timeout: int,
) -> float:
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            audio_format,
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout,
        executable_fd=ffprobe_fd,
        capture=True,
    )
    try:
        value = float(result.stdout.strip())
    except ValueError as exc:
        raise KenBurnsRenderError("narration probe returned an invalid duration") from exc
    if value <= 0 or value > _MAX_DURATION_SECONDS:
        raise KenBurnsRenderError("narration duration is outside the render boundary")
    return value


def _run(
    argv: list[str],
    timeout: int,
    *,
    executable_fd: int,
    capture: bool,
) -> subprocess.CompletedProcess[str]:
    executable = argv[0]
    try:
        _verify_executable_identity(executable, executable_fd)
        with tempfile.TemporaryFile() as captured:
            result = subprocess.run(
                argv,
                shell=False,
                check=True,
                stdout=captured if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False,
                timeout=timeout,
                env={"PATH": "/usr/bin:/bin"},
                executable=executable,
            )
            stdout = ""
            if capture:
                size = captured.tell()
                if size > _MAX_COMMAND_OUTPUT_BYTES:
                    raise KenBurnsRenderError("local media command output exceeded its ceiling")
                captured.seek(0)
                stdout = captured.read(_MAX_COMMAND_OUTPUT_BYTES + 1).decode("utf-8", "strict")
        _verify_executable_identity(executable, executable_fd)
        return subprocess.CompletedProcess(result.args, result.returncode, stdout=stdout, stderr="")
    except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
        raise KenBurnsRenderError("local media command failed") from exc


def _validate_image_dimensions(path: Path, suffix: str) -> int:
    with path.open("rb") as handle:
        header = handle.read(min(_MAX_STILL_BYTES, 1024 * 1024))
    try:
        if suffix == ".png":
            if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
                raise ValueError
            width, height = (
                int.from_bytes(header[16:20], "big"),
                int.from_bytes(header[20:24], "big"),
            )
        elif suffix == ".ppm":
            tokens = re.findall(rb"(?:^|\s)([^#\s]+)", re.sub(rb"#[^\r\n]*", b"", header))
            if len(tokens) < 4 or tokens[0] not in {b"P3", b"P6"}:
                raise ValueError
            width, height = int(tokens[1]), int(tokens[2])
        else:
            width, height = _jpeg_dimensions(header)
    except (IndexError, ValueError) as exc:
        raise KenBurnsRenderError("still input has an invalid image header") from exc
    if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
        raise KenBurnsRenderError("still input exceeds the decoded pixel ceiling")
    return width * height


def _jpeg_dimensions(header: bytes) -> tuple[int, int]:
    if header[:2] != b"\xff\xd8":
        raise ValueError
    offset = 2
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 9 <= len(header):
        if header[offset] != 0xFF:
            offset += 1
            continue
        marker = header[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(header):
            break
        length = int.from_bytes(header[offset : offset + 2], "big")
        if length < 2 or offset + length > len(header):
            break
        if marker in start_of_frame:
            return (
                int.from_bytes(header[offset + 5 : offset + 7], "big"),
                int.from_bytes(header[offset + 3 : offset + 5], "big"),
            )
        offset += length
    raise ValueError


def _copy_regular_file(source: str, destination: Path, max_bytes: int) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise KenBurnsRenderError("render input is unavailable") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > max_bytes:
            raise KenBurnsRenderError("render input must be one bounded regular file")
        with (
            os.fdopen(descriptor, "rb", closefd=False) as source_file,
            destination.open("xb") as out,
        ):
            os.chmod(destination, 0o600)
            while chunk := source_file.read(_COPY_CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise KenBurnsRenderError("render input exceeds its byte ceiling")
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
    finally:
        os.close(descriptor)
    return digest.hexdigest(), total


def _write_private_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _private_output_dir(value: str) -> tuple[Path, int]:
    path = Path(value)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("output_dir must be an existing directory")
    resolved = path.resolve()
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("output_dir must be private and owned by the current user")
        _verify_directory_identity(resolved, descriptor)
    except Exception:
        os.close(descriptor)
        raise
    return resolved, descriptor


def _verify_directory_identity(path: Path, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    current = path.stat(follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise KenBurnsRenderError("output directory identity changed")


def _open_executable(value: str, expected_name: str) -> tuple[str, int]:
    path = Path(value)
    if not path.is_absolute() or path.name != expected_name:
        raise ValueError(f"{expected_name} must be an absolute canonical executable")
    resolved = path.resolve(strict=True)
    if not any(resolved.is_relative_to(root) for root in _APPROVED_EXECUTABLE_ROOTS):
        raise ValueError(f"{expected_name} is outside approved installation roots")
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        os.close(descriptor)
        raise ValueError(f"{expected_name} is not executable")
    return str(resolved), descriptor


def _verify_executable_identity(path: str, descriptor: int) -> None:
    """Reject executable replacement around invocation on platforms without fexecve."""
    opened = os.fstat(descriptor)
    current = os.stat(path, follow_symlinks=False)
    opened_identity = (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
    )
    current_identity = (
        current.st_dev,
        current.st_ino,
        current.st_mode,
        current.st_size,
        current.st_mtime_ns,
    )
    if opened_identity != current_identity:
        raise KenBurnsRenderError("local media executable identity changed")


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded canonical identifier")
    return value


def _passive_suffix(path: str, formats: dict[str, str], label: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix not in formats:
        raise ValueError(f"{label} input format is not allowed")
    return suffix


def _validate_dimensions(width: int, height: int, fps: int, timeout: int) -> None:
    if not 16 <= width <= 3840 or not 16 <= height <= 2160 or width % 2 or height % 2:
        raise ValueError("render dimensions must be bounded positive even integers")
    if not 1 <= fps <= 60 or not 1 <= timeout <= 1800:
        raise ValueError("render fps or timeout is outside its boundary")


def _verify_file_digest(path: str, expected: str, max_bytes: int) -> None:
    observed = _hash_file(Path(path), max_bytes)
    if not hmac.compare_digest(observed, expected):
        raise KenBurnsRenderError("render artifact file digest mismatch")


def _hash_file(path: Path, max_bytes: int) -> str:
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise KenBurnsRenderError("render artifact file is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise KenBurnsRenderError("render artifact must be one regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while chunk := handle.read(_COPY_CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise KenBurnsRenderError("render artifact exceeds its byte ceiling")
                digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _timeline_digest(timeline: tuple[TimelineEntry, ...]) -> str:
    payload = json.dumps(
        [entry.model_dump(mode="json") for entry in timeline],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_digest(manifest: KenBurnsRenderManifest, integrity_key: bytes) -> str:
    payload = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hmac.new(integrity_key, payload, hashlib.sha256).hexdigest()


def _integrity_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < _MIN_INTEGRITY_KEY_BYTES:
        raise ValueError("integrity_key must contain at least 32 bytes")
    return value


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unique(values: Iterable[str], label: str) -> None:
    rows = tuple(values)
    if len(rows) != len(set(rows)):
        raise ValueError(f"{label} must be unique")


__all__ = [
    "KenBurnsRenderArtifact",
    "KenBurnsRenderError",
    "KenBurnsRenderManifest",
    "RenderedCaption",
    "RenderedInput",
    "SceneStillInput",
    "render_ken_burns_documentary",
]
