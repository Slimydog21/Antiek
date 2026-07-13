"""Materialize measured local AudibleRun spans into one trusted PCM track."""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .local_audible_bridge import LocalAudibleInputs
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH

_MAX_SPANS = 4096
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_APPROVED_EXECUTABLE_ROOTS = (Path("/opt/homebrew/Cellar/ffmpeg"), Path("/usr/bin"))
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class LocalAudibleProductionError(RuntimeError):
    """Audible audio inputs or published evidence failed closed."""


class _Model(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", revalidate_instances="always", allow_inf_nan=False
    )


class AudibleAudioSource(_Model):
    sequence: int = Field(ge=0)
    request_id: str
    paragraph_id: str
    chapter_id: str
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    duration_seconds: float = Field(gt=0)


class LocalAudibleProductionManifest(_Model):
    schema_version: Literal["antiek.local-audible-production.v1"] = (
        "antiek.local-audible-production.v1"
    )
    asset_id: str
    revision_id: str
    input_digest: str = Field(pattern="^[0-9a-f]{64}$")
    audible_run_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    output_path: str
    output_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    output_bytes: int = Field(gt=44, le=_MAX_TOTAL_BYTES)
    duration_seconds: float = Field(gt=0, le=45 * 60)
    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(ge=8_000, le=48_000)
    channels: Literal[1, 2]
    cost_usd: Literal[0] = 0
    sources: tuple[AudibleAudioSource, ...] = Field(min_length=1, max_length=_MAX_SPANS)

    @model_validator(mode="after")
    def timeline_authority_is_complete(self) -> LocalAudibleProductionManifest:
        if not Path(self.output_path).is_absolute():
            raise ValueError("audible output path must be absolute")
        if tuple(row.sequence for row in self.sources) != tuple(range(len(self.sources))):
            raise ValueError("audible source sequence must be contiguous")
        if len({row.request_id for row in self.sources}) != len(self.sources):
            raise ValueError("audible source request ids must be unique")
        if len({row.paragraph_id for row in self.sources}) != len(self.sources):
            raise ValueError("audible source paragraph ids must be unique")
        expected = round(sum(row.duration_seconds for row in self.sources), 3)
        if self.duration_seconds != expected:
            raise ValueError("audible duration is not bound to measured spans")
        return self


class LocalAudibleProductionArtifact(_Model):
    manifest: LocalAudibleProductionManifest
    manifest_mac: str = Field(pattern="^[0-9a-f]{64}$")

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(
        cls, payload: str | bytes, integrity_key: bytes
    ) -> LocalAudibleProductionArtifact:
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_MANIFEST_BYTES:
            raise LocalAudibleProductionError("audible production manifest is too large")
        try:
            artifact = cls.model_validate_json(payload)
        except Exception:
            raise LocalAudibleProductionError("audible production manifest is invalid") from None
        if not hmac.compare_digest(
            artifact.manifest_mac, _manifest_mac(artifact.manifest, integrity_key)
        ):
            raise LocalAudibleProductionError("audible production manifest MAC is invalid")
        size, digest = _private_file_evidence(artifact.manifest.output_path, _MAX_TOTAL_BYTES)
        if size != artifact.manifest.output_bytes or not hmac.compare_digest(
            digest, artifact.manifest.output_sha256
        ):
            raise LocalAudibleProductionError("audible production output evidence conflicts")
        return artifact


def produce_local_audible_track(
    inputs: LocalAudibleInputs,
    *,
    output_dir: str,
    integrity_key: bytes,
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    sample_rate_hz: int = 24_000,
    channels: Literal[1, 2] = 1,
    timeout_seconds: int = 300,
    publication_id: str | None = None,
) -> LocalAudibleProductionArtifact:
    if (
        not isinstance(inputs, LocalAudibleInputs)
        or not inputs.spans
        or len(inputs.spans) > _MAX_SPANS
        or inputs.cost_usd != 0
        or not 8_000 <= sample_rate_hz <= 48_000
        or channels not in {1, 2}
        or not 1 <= timeout_seconds <= 900
    ):
        raise ValueError("local audible production inputs are invalid")
    if inputs.audible_run.manifest.total_duration_seconds != round(
        sum(row.duration_seconds for row in inputs.spans), 3
    ):
        raise ValueError("local audible timing authority conflicts")
    root = _private_directory(output_dir)
    ffmpeg = _executable(ffmpeg_path)
    ffprobe = _executable(ffprobe_path)
    publication_suffix = ""
    if publication_id is not None:
        if not isinstance(publication_id, str) or not _ID.fullmatch(publication_id):
            raise ValueError("local audible publication identity is invalid")
        publication_suffix = f"-{publication_id}"
    destination = root / (
        f"{inputs.asset_id}-{inputs.revision_id}-audible-{inputs.input_digest[:16]}"
        f"{publication_suffix}"
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"audible destination already exists: {destination.name}")
    staging = Path(tempfile.mkdtemp(prefix=".audible-", dir=root))
    published = False
    try:
        os.chmod(staging, 0o700)
        staged: list[Path] = []
        source_rows: list[AudibleAudioSource] = []
        identities: set[tuple[int, int]] = set()
        total_bytes = 0
        for row in inputs.spans:
            target = staging / f"source-{row.sequence:04d}.wav"
            size, digest, identity = _copy_private(row.path, target)
            if not hmac.compare_digest(digest, row.sha256) or identity in identities:
                raise LocalAudibleProductionError("audible source evidence conflicts")
            identities.add(identity)
            total_bytes += size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise LocalAudibleProductionError("audible sources exceed aggregate ceiling")
            duration, codec, rate, actual_channels = _probe(ffprobe, target, timeout_seconds)
            if (
                duration != row.duration_seconds
                or codec != "pcm_s16le"
                or rate != sample_rate_hz
                or actual_channels != channels
            ):
                raise LocalAudibleProductionError("audible source audio shape conflicts")
            staged.append(target)
            source_rows.append(
                AudibleAudioSource(
                    sequence=row.sequence,
                    request_id=row.request_id,
                    paragraph_id=row.paragraph_id,
                    chapter_id=row.chapter_id,
                    sha256=row.sha256,
                    duration_seconds=row.duration_seconds,
                )
            )
        output = staging / "audible.wav"
        argv = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        for source in staged:
            argv.extend(["-protocol_whitelist", "file,pipe", "-i", str(source)])
        joined = "".join(f"[{index}:a]" for index in range(len(staged)))
        argv.extend(
            [
                "-filter_complex",
                f"{joined}concat=n={len(staged)}:v=0:a=1[a]",
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
        os.chmod(output, 0o600, follow_symlinks=False)
        duration, codec, rate, actual_channels = _probe(ffprobe, output, timeout_seconds)
        expected_duration = round(sum(row.duration_seconds for row in inputs.spans), 3)
        if (
            duration != expected_duration
            or codec != "pcm_s16le"
            or rate != sample_rate_hz
            or actual_channels != channels
        ):
            raise LocalAudibleProductionError("audible output probe conflicts")
        output_size, output_digest = _private_file_evidence(output, _MAX_TOTAL_BYTES)
        final_output = destination / "audible.wav"
        manifest = LocalAudibleProductionManifest(
            asset_id=inputs.asset_id,
            revision_id=inputs.revision_id,
            input_digest=inputs.input_digest,
            audible_run_sha256=inputs.audible_run.manifest_sha256,
            output_path=str(final_output),
            output_sha256=output_digest,
            output_bytes=output_size,
            duration_seconds=duration,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            sources=tuple(source_rows),
        )
        artifact = LocalAudibleProductionArtifact(
            manifest=manifest, manifest_mac=_manifest_mac(manifest, integrity_key)
        )
        manifest_path = staging / "audible.json"
        manifest_path.write_text(artifact.to_json(), encoding="ascii")
        os.chmod(manifest_path, 0o600, follow_symlinks=False)
        _fsync_file(manifest_path)
        _fsync_directory(staging)
        try:
            os.rename(staging, destination)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            raise FileExistsError(
                f"audible destination already exists: {destination.name}"
            ) from None
        published = True
        _fsync_directory(root)
        return LocalAudibleProductionArtifact.reopen(
            (destination / "audible.json").read_bytes(), integrity_key
        )
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def _copy_private(value: str, destination: Path) -> tuple[int, str, tuple[int, int]]:
    absolute = os.path.abspath(value)
    if absolute != os.path.realpath(value):
        raise LocalAudibleProductionError("audible source cannot traverse symlinks")
    descriptor = _open_private(absolute, _MAX_SOURCE_BYTES)
    try:
        info = os.fstat(descriptor)
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
        return info.st_size, digest.hexdigest(), (info.st_dev, info.st_ino)
    finally:
        os.close(descriptor)


def _private_file_evidence(value: str | Path, maximum: int) -> tuple[int, str]:
    descriptor = _open_private(str(value), maximum)
    try:
        info = os.fstat(descriptor)
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        return info.st_size, digest.hexdigest()
    finally:
        os.close(descriptor)


def _open_private(value: str, maximum: int) -> int:
    try:
        descriptor = os.open(value, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
    except OSError:
        raise LocalAudibleProductionError("audible file is unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
        or not 44 <= info.st_size <= maximum
    ):
        os.close(descriptor)
        raise LocalAudibleProductionError("audible file is not private and bounded")
    return descriptor


def _probe(executable: str, path: Path, timeout: int) -> tuple[float, str, int, int]:
    result = _run(
        [
            executable,
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
        if len(streams) != 1 or len(audio) != 1:
            raise ValueError
        return (
            round(float(payload["format"]["duration"]), 3),
            str(audio[0]["codec_name"]),
            int(audio[0]["sample_rate"]),
            int(audio[0]["channels"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise LocalAudibleProductionError("audible probe output is invalid") from None


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
            shell=False,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError):
        raise LocalAudibleProductionError("audible media process failed") from None


def _private_directory(value: str) -> Path:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("audible output directory is unavailable") from None
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.resolve() != path
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("audible output directory must be private")
    return path


def _executable(value: str) -> str:
    path = Path(value).resolve(strict=True)
    if (
        not path.is_file()
        or not os.access(path, os.X_OK)
        or not any(path.is_relative_to(root) for root in _APPROVED_EXECUTABLE_ROOTS)
    ):
        raise ValueError("audible executable is outside approved roots")
    return str(path)


def _manifest_mac(manifest: LocalAudibleProductionManifest, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("audible integrity key must contain at least 32 bytes")
    payload = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "AudibleAudioSource",
    "LocalAudibleProductionArtifact",
    "LocalAudibleProductionError",
    "LocalAudibleProductionManifest",
    "produce_local_audible_track",
]
