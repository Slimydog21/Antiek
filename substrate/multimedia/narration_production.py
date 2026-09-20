"""Materialize verified chapter audio into one renderer-ready narration track."""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts.multimedia import GeneratedFile
from .audio_assembly import ChapterAudio
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH

_MAX_CHAPTERS = 64
_MAX_FILE_BYTES = 512 * 1024 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_APPROVED_EXECUTABLE_ROOTS = (Path("/opt/homebrew/Cellar/ffmpeg"), Path("/usr/bin"))
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class NarrationProductionError(RuntimeError):
    """Narration inputs or output failed a production authority check."""


class _Model(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", revalidate_instances="always", allow_inf_nan=False
    )


class NarrationSource(_Model):
    sequence: int = Field(ge=0)
    chapter_id: str
    audio_file_id: str
    path: str
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    duration_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def identity_is_bounded(self) -> NarrationSource:
        _identifier(self.chapter_id, "chapter_id")
        _identifier(self.audio_file_id, "audio_file_id")
        if not Path(self.path).is_absolute():
            raise ValueError("narration source path must be absolute")
        if self.duration_seconds != round(self.duration_seconds, 3):
            raise ValueError("narration source duration must use millisecond precision")
        return self


class NarrationChapterBinding(_Model):
    chapter_id: str
    script_line_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]
    paragraph_ids: tuple[str, ...]

    @model_validator(mode="after")
    def identifiers_are_bounded(self) -> NarrationChapterBinding:
        _identifier(self.chapter_id, "chapter_id")
        for field, values in (
            ("script_line_id", self.script_line_ids),
            ("source_chunk_id", self.source_chunk_ids),
            ("paragraph_id", self.paragraph_ids),
        ):
            for value in values:
                _identifier(value, field)
        return self


class NarrationProductionManifest(_Model):
    schema_version: Literal["antiek.narration-production.v1"] = (
        "antiek.narration-production.v1"
    )
    asset_id: str
    revision_id: str
    output_path: str
    output_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    duration_seconds: float = Field(gt=0, le=45 * 60)
    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(ge=8_000, le=48_000)
    channels: Literal[1, 2]
    sources: tuple[NarrationSource, ...] = Field(min_length=1, max_length=_MAX_CHAPTERS)
    chapter_bindings: tuple[NarrationChapterBinding, ...] = Field(
        default_factory=tuple, max_length=_MAX_CHAPTERS
    )

    @model_validator(mode="after")
    def sources_are_complete(self) -> NarrationProductionManifest:
        _identifier(self.asset_id, "asset_id")
        _identifier(self.revision_id, "revision_id")
        if not Path(self.output_path).is_absolute():
            raise ValueError("narration output path must be absolute")
        if self.duration_seconds != round(self.duration_seconds, 3):
            raise ValueError("narration duration must use millisecond precision")
        if tuple(row.sequence for row in self.sources) != tuple(range(len(self.sources))):
            raise ValueError("narration source sequence is not contiguous")
        if len({row.chapter_id for row in self.sources}) != len(self.sources):
            raise ValueError("narration chapter ids must be unique")
        if len({row.audio_file_id for row in self.sources}) != len(self.sources):
            raise ValueError("narration audio file ids must be unique")
        if self.chapter_bindings and tuple(
            row.chapter_id for row in self.chapter_bindings
        ) != tuple(row.chapter_id for row in self.sources):
            raise ValueError("narration chapter bindings conflict with sources")
        expected = round(sum(row.duration_seconds for row in self.sources), 3)
        if expected != self.duration_seconds:
            raise ValueError("narration duration is not bound to its chapters")
        return self


class NarrationProductionArtifact(_Model):
    manifest: NarrationProductionManifest
    manifest_mac: str = Field(pattern="^[0-9a-f]{64}$")

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(cls, payload: str | bytes, integrity_key: bytes) -> NarrationProductionArtifact:
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_MANIFEST_BYTES:
            raise NarrationProductionError("narration manifest exceeds its byte ceiling")
        artifact = cls.model_validate_json(payload)
        if not hmac.compare_digest(artifact.manifest_mac, _manifest_mac(artifact.manifest, integrity_key)):
            raise NarrationProductionError("narration manifest MAC is invalid")
        _verify_file(artifact.manifest.output_path, artifact.manifest.output_sha256)
        for row in artifact.manifest.sources:
            _verify_file(row.path, row.sha256)
        return artifact


def produce_narration_track(
    *,
    asset_id: str,
    revision_id: str,
    chapters: tuple[ChapterAudio, ...],
    generated_files: tuple[GeneratedFile, ...],
    chapter_paths: Mapping[str, str],
    output_dir: str,
    integrity_key: bytes,
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
    timeout_seconds: int = 300,
    publication_id: str | None = None,
) -> NarrationProductionArtifact:
    asset_id = _identifier(asset_id, "asset_id")
    revision_id = _identifier(revision_id, "revision_id")
    if not chapters or len(chapters) > _MAX_CHAPTERS:
        raise ValueError("narration requires one through 64 chapters")
    if tuple(row.sequence for row in chapters) != tuple(range(len(chapters))):
        raise ValueError("chapter sequence must be contiguous")
    expected_offset = 0.0
    for chapter in chapters:
        declared_end = chapter.end_offset_seconds
        if (
            not math.isfinite(chapter.start_offset_seconds)
            or not math.isfinite(declared_end)
            or chapter.start_offset_seconds != expected_offset
            or declared_end
            != round(chapter.start_offset_seconds + chapter.duration_seconds, 3)
        ):
            raise ValueError("chapter timeline must be contiguous and duration-bound")
        expected_offset = declared_end
    expected_ids = tuple(row.audio_file_id for row in chapters)
    if set(chapter_paths) != set(expected_ids) or len(expected_ids) != len(set(expected_ids)):
        raise ValueError("chapter paths must exactly cover unique audio file ids")
    if len({row.file_id for row in generated_files}) != len(generated_files):
        raise ValueError("generated file ids must be globally unique")
    audio_files = tuple(row for row in generated_files if row.kind == "audio")
    files = {row.file_id: row for row in audio_files}
    if set(files) != set(expected_ids):
        raise ValueError("generated audio files must exactly cover chapters")
    if not 8_000 <= sample_rate_hz <= 48_000 or channels not in {1, 2}:
        raise ValueError("narration audio shape is invalid")
    root = _private_directory(output_dir)
    publication_suffix = (
        "" if publication_id is None else f"-{_identifier(publication_id, 'publication_id')}"
    )
    destination = root / f"{asset_id}-{revision_id}-narration{publication_suffix}"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"narration destination already exists: {destination.name}")
    ffmpeg = _executable(ffmpeg_path)
    ffprobe = _executable(ffprobe_path)
    staging = Path(tempfile.mkdtemp(prefix=".narration-", dir=root))
    published = False
    try:
        os.chmod(staging, 0o700)
        sources: list[NarrationSource] = []
        staged_sources: list[Path] = []
        identities: set[tuple[int, int]] = set()
        total_bytes = 0
        for chapter in chapters:
            generated = files[chapter.audio_file_id]
            if (
                generated.duration_seconds is None
                or not math.isfinite(chapter.duration_seconds)
                or chapter.duration_seconds <= 0
                or generated.duration_seconds != chapter.duration_seconds
            ):
                raise NarrationProductionError(
                    "chapter duration conflicts with generated file authority"
                )
            staged_source = staging / f"source-{chapter.sequence:04d}.audio"
            path, digest, size, identity = _copy_verified_private_file(
                chapter_paths[chapter.audio_file_id], generated.sha256, staged_source
            )
            actual_duration, _, _, _ = _probe_audio(ffprobe, staged_source, timeout_seconds)
            if actual_duration != chapter.duration_seconds:
                raise NarrationProductionError(
                    "chapter audio duration conflicts with materialized bytes"
                )
            if identity in identities:
                raise NarrationProductionError("chapter audio paths cannot alias one inode")
            identities.add(identity)
            total_bytes += size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise NarrationProductionError("narration sources exceed aggregate byte ceiling")
            sources.append(
                NarrationSource(
                    sequence=chapter.sequence,
                    chapter_id=_identifier(chapter.chapter_id, "chapter_id"),
                    audio_file_id=_identifier(chapter.audio_file_id, "audio_file_id"),
                    path=path,
                    sha256=digest,
                    duration_seconds=chapter.duration_seconds,
                )
            )
            staged_sources.append(staged_source)
        output = staging / "narration.wav"
        argv = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        for source in staged_sources:
            argv.extend(["-protocol_whitelist", "file,pipe", "-i", str(source)])
        joined = "".join(f"[{index}:a]" for index in range(len(sources)))
        argv.extend(
            [
                "-filter_complex",
                f"{joined}concat=n={len(sources)}:v=0:a=1[a]",
                "-map",
                "[a]",
                "-ar",
                str(sample_rate_hz),
                "-ac",
                str(channels),
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        _run(argv, timeout_seconds)
        duration, codec, probed_rate, probed_channels = _probe_audio(
            ffprobe, output, timeout_seconds
        )
        expected_duration = round(sum(row.duration_seconds for row in sources), 3)
        if duration != expected_duration:
            raise NarrationProductionError("materialized narration duration drifted from chapters")
        if codec != "pcm_s16le" or probed_rate != sample_rate_hz or probed_channels != channels:
            raise NarrationProductionError("materialized narration shape is invalid")
        os.chmod(output, 0o600)
        output_sha = _hash_file(output)
        manifest = NarrationProductionManifest(
            asset_id=asset_id,
            revision_id=revision_id,
            output_path=str(destination / "narration.wav"),
            output_sha256=output_sha,
            duration_seconds=expected_duration,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            sources=tuple(sources),
            chapter_bindings=tuple(
                NarrationChapterBinding(
                    chapter_id=chapter.chapter_id,
                    script_line_ids=chapter.script_line_ids,
                    source_chunk_ids=chapter.source_chunk_ids,
                    paragraph_ids=chapter.paragraph_ids,
                )
                for chapter in chapters
            ),
        )
        artifact = NarrationProductionArtifact(
            manifest=manifest,
            manifest_mac=_manifest_mac(manifest, integrity_key),
        )
        (staging / "narration.json").write_text(artifact.to_json())
        os.chmod(staging / "narration.json", 0o600)
        for source in staged_sources:
            source.unlink()
        try:
            os.rename(staging, destination)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            raise FileExistsError(
                f"narration destination already exists: {destination.name}"
            ) from None
        published = True
        try:
            return NarrationProductionArtifact.reopen(
                (destination / "narration.json").read_bytes(), integrity_key
            )
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def _copy_verified_private_file(
    value: str, expected: str, destination: Path
) -> tuple[str, str, int, tuple[int, int]]:
    absolute = os.path.abspath(value)
    if absolute != os.path.realpath(value):
        raise NarrationProductionError("chapter audio cannot traverse symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError:
        raise NarrationProductionError("chapter audio is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= _MAX_FILE_BYTES
        ):
            raise NarrationProductionError("chapter audio is not private and bounded")
        output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        try:
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    view = view[os.write(output, view) :]
            os.fsync(output)
        finally:
            os.close(output)
    finally:
        os.close(descriptor)
    actual = digest.hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise NarrationProductionError("chapter audio digest conflicts with manifest")
    return absolute, actual, info.st_size, (info.st_dev, info.st_ino)


def _verify_file(path: str, expected: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise NarrationProductionError("narration file is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= _MAX_FILE_BYTES
        ):
            raise NarrationProductionError("narration file is not private and bounded")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if not hmac.compare_digest(digest.hexdigest(), expected):
        raise NarrationProductionError("narration file digest is invalid")


def _private_directory(value: str) -> Path:
    root = Path(value)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("narration output directory must be private")
    return root.resolve()


def _executable(value: str) -> str:
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK) or not any(path.is_relative_to(root) for root in _APPROVED_EXECUTABLE_ROOTS):
        raise ValueError("media executable is outside approved roots")
    return str(path)


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise NarrationProductionError("narration media process failed") from None


def _probe_audio(ffprobe: str, path: Path, timeout: int) -> tuple[float, str, int, int]:
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        timeout,
    )
    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        audio = [row for row in streams if row["codec_type"] == "audio"]
        if len(audio) != 1 or len(streams) != 1:
            raise ValueError
        return (
            round(float(payload["format"]["duration"]), 3),
            str(audio[0]["codec_name"]),
            int(audio[0]["sample_rate"]),
            int(audio[0]["channels"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise NarrationProductionError("narration output probe is invalid") from None


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_mac(manifest: NarrationProductionManifest, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("narration integrity key must contain at least 32 bytes")
    payload = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


__all__ = [
    "NarrationChapterBinding",
    "NarrationProductionArtifact",
    "NarrationProductionError",
    "produce_narration_track",
]
