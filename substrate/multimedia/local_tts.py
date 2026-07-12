"""Trusted zero-network local speech synthesis into replayable PCM WAV artifacts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .chapter_tts_production import PreparedChapterTTSRequest
from .local_audible_tts import PreparedAudibleSpanTTSRequest

DatabaseRow = tuple[object, ...]

LocalSpeechRequest = PreparedChapterTTSRequest | PreparedAudibleSpanTTSRequest

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_TEXT_BYTES = 256 * 1024
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_tts_artifacts (
 request_id TEXT PRIMARY KEY, request_body_digest TEXT NOT NULL,
 config_digest TEXT NOT NULL, status TEXT NOT NULL,
 pending_path TEXT NOT NULL, output_path TEXT NOT NULL,
 output_sha256 TEXT NOT NULL, duration_seconds DOUBLE NOT NULL,
 sample_rate_hz INTEGER NOT NULL, channels INTEGER NOT NULL,
 synthesizer_digest TEXT NOT NULL, probe_digest TEXT NOT NULL,
 created_at TEXT NOT NULL, row_mac TEXT NOT NULL)
"""


class LocalTTSError(RuntimeError):
    """Local synthesis configuration, execution, or persisted evidence failed."""


class LocalTTSOutcomeUnknown(LocalTTSError):
    """A local process may have produced bytes and requires explicit recovery."""


def _number(value: object) -> float:
    if not isinstance(value, (str, int, float)):
        raise LocalTTSError("stored local TTS numeric evidence is invalid")
    return float(value)


def _integer(value: object) -> int:
    if not isinstance(value, (str, int, float)):
        raise LocalTTSError("stored local TTS numeric evidence is invalid")
    return int(value)


@dataclass(frozen=True)
class LocalTTSConfig:
    synthesizer_path: str
    ffprobe_path: str
    output_dir: str
    voice: str = "Samantha"
    words_per_minute: int = 180
    sample_rate_hz: int = 24_000
    channels: Literal[1, 2] = 1
    timeout_seconds: int = 300


@dataclass(frozen=True)
class LocalTTSArtifact:
    request_id: str
    request_body_digest: str
    config_digest: str
    output_path: str
    output_sha256: str
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    synthesizer_digest: str
    probe_digest: str
    created_at: str


class LocalTTSAdapter:
    """Explicitly configured macOS ``say`` adapter with no network fallback."""

    def __init__(self, *, config: LocalTTSConfig, db_path: str, signing_key: bytes) -> None:
        if not db_path or not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("local TTS persistence configuration is invalid")
        if (
            not _ID.fullmatch(config.voice)
            or not 80 <= config.words_per_minute <= 450
            or not 8_000 <= config.sample_rate_hz <= 48_000
            or config.channels not in {1, 2}
            or not 1 <= config.timeout_seconds <= 900
        ):
            raise ValueError("local TTS synthesis configuration is invalid")
        self._config = config
        self._db_path = _private_db_path(db_path)
        self._key = signing_key
        self._synthesizer, self._synthesizer_digest = _trusted_executable(
            config.synthesizer_path
        )
        self._probe, self._probe_digest = _trusted_executable(config.ffprobe_path)
        self._root = _private_directory(config.output_dir)
        self._verify_voice()
        self._config_digest = hashlib.sha256(
            _canonical(
                {
                    "channels": config.channels,
                    "ffprobe_digest": self._probe_digest,
                    "sample_rate_hz": config.sample_rate_hz,
                    "schema_version": "antiek.local-tts-config.v1",
                    "synthesizer_digest": self._synthesizer_digest,
                    "timeout_seconds": config.timeout_seconds,
                    "voice": config.voice,
                    "words_per_minute": config.words_per_minute,
                }
            )
        ).hexdigest()

    def synthesize(
        self, request: LocalSpeechRequest, *, now: datetime
    ) -> LocalTTSArtifact:
        request = _request(request)
        self._verify_executables()
        request_id = _request_id(request, self._config_digest)
        existing = self._load(request_id)
        if existing is not None:
            if existing[3] == "succeeded":
                return self._reopen(existing, request)
            if existing[3] == "producing":
                raise LocalTTSOutcomeUnknown("local TTS synthesis outcome is unknown")
            raise LocalTTSError("local TTS synthesis previously failed")
        pending = self._root / f".{request_id}.pending.wav"
        output = self._root / f"{request_id}.wav"
        timestamp = _timestamp(now)
        values: list[object] = [
            request_id,
            request.body_digest,
            self._config_digest,
            "producing",
            str(pending),
            str(output),
            "",
            0.0,
            self._config.sample_rate_hz,
            self._config.channels,
            self._synthesizer_digest,
            self._probe_digest,
            timestamp,
        ]
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_tts.begin") as connection:
            connection.execute(_DDL)
            connection.execute("BEGIN TRANSACTION")
            try:
                prior = connection.execute(
                    "SELECT * FROM multimedia_local_tts_artifacts WHERE request_id=?",
                    [request_id],
                ).fetchone()
                if prior is not None:
                    connection.execute("ROLLBACK")
                    if prior[3] == "succeeded":
                        return self._reopen(prior, request)
                    raise LocalTTSOutcomeUnknown("local TTS synthesis outcome is unknown")
                connection.execute(
                    "INSERT INTO multimedia_local_tts_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [*values, _mac(values, self._key)],
                )
                connection.execute("COMMIT")
            except Exception:
                with suppress(Exception):
                    connection.execute("ROLLBACK")
                raise
        try:
            self._invoke(request.text, pending)
            artifact = self._finalize(request, values, pending, output)
        except LocalTTSOutcomeUnknown:
            raise
        except Exception as exc:
            if pending.exists() or output.exists():
                raise LocalTTSOutcomeUnknown(
                    "local TTS output requires explicit recovery"
                ) from exc
            self._mark_failed(values)
            raise LocalTTSError("local TTS synthesis failed") from exc
        return artifact

    def reopen(self, request: LocalSpeechRequest) -> LocalTTSArtifact:
        """Verify an existing successful artifact without invoking synthesis."""
        request = _request(request)
        self._verify_executables()
        row = self._load(_request_id(request, self._config_digest))
        if row is None:
            raise LocalTTSError("local TTS artifact is unavailable")
        return self._reopen(row, request)

    def recover(
        self, request: LocalSpeechRequest
    ) -> LocalTTSArtifact:
        """Finalize a validated pending WAV without invoking synthesis again."""
        request = _request(request)
        self._verify_executables()
        request_id = _request_id(request, self._config_digest)
        row = self._load(request_id)
        if row is None:
            raise LocalTTSError("local TTS artifact is unavailable")
        if row[3] == "succeeded":
            return self._reopen(row, request)
        if row[3] != "producing":
            raise LocalTTSError("local TTS synthesis cannot be recovered")
        self._verify_row(row, request)
        pending, output = Path(str(row[4])), Path(str(row[5]))
        if not pending.exists() and not output.exists():
            raise LocalTTSOutcomeUnknown("local TTS pending output is unavailable")
        return self._finalize(request, list(row[:13]), pending, output)

    def _invoke(self, text: str, pending: Path) -> None:
        if pending.exists() or pending.is_symlink():
            raise LocalTTSOutcomeUnknown("local TTS pending output already exists")
        with tempfile.TemporaryDirectory(prefix=".local-tts-", dir=self._root) as directory:
            staging = Path(directory)
            os.chmod(staging, 0o700)
            source = staging / "narration.txt"
            descriptor = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                payload = text.encode("utf-8")
                view = memoryview(payload)
                while view:
                    view = view[os.write(descriptor, view) :]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            command = [
                self._synthesizer,
                "-v",
                self._config.voice,
                "-r",
                str(self._config.words_per_minute),
                "-o",
                str(pending),
                "--file-format=WAVE",
                f"--data-format=LEI16@{self._config.sample_rate_hz}",
                f"--channels={self._config.channels}",
                "-f",
                str(source),
            ]
            environment = {
                "HOME": str(staging),
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
                "TMPDIR": str(staging),
            }
            try:
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=self._config.timeout_seconds,
                    check=False,
                    shell=False,
                    env=environment,
                )
            except subprocess.TimeoutExpired as exc:
                raise LocalTTSOutcomeUnknown("local TTS synthesis timed out") from exc
            if completed.returncode != 0:
                raise LocalTTSError("local TTS executable rejected synthesis")

    def _finalize(
        self,
        request: LocalSpeechRequest,
        row_values: list[object],
        pending: Path,
        output: Path,
    ) -> LocalTTSArtifact:
        if output.is_symlink() or pending.is_symlink():
            raise LocalTTSError("local TTS output conflicts")
        if output.exists():
            if pending.exists():
                raise LocalTTSError("local TTS output conflicts")
            digest, duration = self._verify_wav(output)
        else:
            _make_private_regular(pending)
            digest, duration = self._verify_wav(pending)
            os.replace(pending, output)
            _fsync_directory(self._root)
        updated = [
            row_values[0], row_values[1], row_values[2], "succeeded",
            row_values[4], row_values[5], digest, duration,
            row_values[8], row_values[9], row_values[10], row_values[11], row_values[12],
        ]
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_tts.complete") as connection:
            connection.execute(_DDL)
            connection.execute("BEGIN TRANSACTION")
            try:
                current = connection.execute(
                    "SELECT * FROM multimedia_local_tts_artifacts WHERE request_id=?",
                    [row_values[0]],
                ).fetchone()
                self._verify_row(current, request)
                if current[3] == "succeeded":
                    connection.execute("COMMIT")
                    return self._reopen(current, request)
                if current[3] != "producing":
                    raise LocalTTSError("local TTS state conflicts")
                connection.execute(
                    "UPDATE multimedia_local_tts_artifacts SET status=?, output_sha256=?, "
                    "duration_seconds=?, row_mac=? WHERE request_id=?",
                    ["succeeded", digest, duration, _mac(updated, self._key), row_values[0]],
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._reopen(tuple([*updated, _mac(updated, self._key)]), request)

    def _verify_wav(self, path: Path) -> tuple[str, float]:
        digest = _private_file_digest(path)
        command = [
            self._probe,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
            "-of", "json",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=30, check=False, shell=False,
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
            payload = json.loads(completed.stdout)
            streams = payload["streams"]
            stream = streams[0]
            duration = round(float(payload["format"]["duration"]), 3)
        except Exception as exc:
            raise LocalTTSError("local TTS output could not be probed") from exc
        if (
            completed.returncode != 0
            or len(streams) != 1
            or stream.get("codec_name") != "pcm_s16le"
            or int(stream.get("sample_rate", 0)) != self._config.sample_rate_hz
            or int(stream.get("channels", 0)) != self._config.channels
            or not 0 < duration <= 45 * 60
        ):
            raise LocalTTSError("local TTS output format conflicts")
        return digest, duration

    def _load(self, request_id: str) -> DatabaseRow | None:
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_tts_artifacts WHERE request_id=?",
                    [request_id],
                ).fetchone()
        except Exception:
            return None

    def _verify_row(self, row: DatabaseRow, request: LocalSpeechRequest) -> None:
        if (
            row is None
            or len(row) != 14
            or not isinstance(row[13], str)
            or not hmac.compare_digest(row[13], _mac(list(row[:13]), self._key))
            or row[0] != _request_id(request, self._config_digest)
            or row[1] != request.body_digest
            or row[2] != self._config_digest
            or row[8] != self._config.sample_rate_hz
            or row[9] != self._config.channels
            or row[10] != self._synthesizer_digest
            or row[11] != self._probe_digest
        ):
            raise LocalTTSError("stored local TTS integrity failed")

    def _reopen(
        self, row: DatabaseRow, request: LocalSpeechRequest
    ) -> LocalTTSArtifact:
        self._verify_executables()
        self._verify_row(row, request)
        if row[3] != "succeeded" or not row[6] or _number(row[7]) <= 0:
            raise LocalTTSError("local TTS artifact is incomplete")
        if not hmac.compare_digest(_private_file_digest(Path(str(row[5]))), str(row[6])):
            raise LocalTTSError("local TTS output digest conflicts")
        actual_digest, actual_duration = self._verify_wav(Path(str(row[5])))
        if (
            not hmac.compare_digest(actual_digest, str(row[6]))
            or actual_duration != round(_number(row[7]), 3)
        ):
            raise LocalTTSError("local TTS output evidence conflicts")
        return LocalTTSArtifact(
            request_id=str(row[0]), request_body_digest=str(row[1]),
            config_digest=str(row[2]), output_path=str(row[5]), output_sha256=str(row[6]),
            duration_seconds=_number(row[7]), sample_rate_hz=_integer(row[8]),
            channels=_integer(row[9]),
            synthesizer_digest=str(row[10]), probe_digest=str(row[11]), created_at=str(row[12]),
        )

    def _mark_failed(self, values: list[object]) -> None:
        failed = [*values]
        failed[3] = "failed"
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_tts.fail") as connection:
            connection.execute(_DDL)
            connection.execute(
                "UPDATE multimedia_local_tts_artifacts SET status=?, row_mac=? WHERE request_id=?",
                ["failed", _mac(failed, self._key), values[0]],
            )

    def _verify_executables(self) -> None:
        if (
            not hmac.compare_digest(
                _hash_file(Path(self._synthesizer), _MAX_EXECUTABLE_BYTES),
                self._synthesizer_digest,
            )
            or not hmac.compare_digest(
                _hash_file(Path(self._probe), _MAX_EXECUTABLE_BYTES), self._probe_digest
            )
        ):
            raise LocalTTSError("local TTS executable identity changed")

    def _verify_voice(self) -> None:
        try:
            completed = subprocess.run(
                [self._synthesizer, "-v", "?"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
                check=False,
                shell=False,
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
            output = completed.stdout[: 1024 * 1024].decode("utf-8", errors="strict")
        except Exception as exc:
            raise ValueError("local TTS voice inventory is unavailable") from exc
        if completed.returncode != 0 or not any(
            line.split(maxsplit=1)[0] == self._config.voice
            for line in output.splitlines()
            if line.strip()
        ):
            raise ValueError("local TTS voice is unavailable")


def _request(value: LocalSpeechRequest) -> LocalSpeechRequest:
    if (
        not isinstance(value, (PreparedChapterTTSRequest, PreparedAudibleSpanTTSRequest))
        or value.route_policy != "cheapest"
        or value.provider != "local_executable_tts"
        or value.model != "macos-say-v1"
        or value.endpoint_capability != "text-to-speech"
        or not value.text
        or len(value.text.encode("utf-8")) > _MAX_TEXT_BYTES
    ):
        raise ValueError("local TTS request is invalid")
    return value


def _request_id(request: LocalSpeechRequest, config_digest: str) -> str:
    unit_binding = (
        f"{request.chapter_id}\0{request.paragraph_id}"
        if isinstance(request, PreparedAudibleSpanTTSRequest)
        else request.chapter_id
    )
    return "mmlocaltts_" + hashlib.sha256(
        f"{request.asset_id}\0{request.revision_id}\0{unit_binding}\0"
        f"{request.body_digest}\0{config_digest}".encode()
    ).hexdigest()


def _trusted_executable(value: str) -> tuple[str, str]:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("local TTS executable path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
        parent = resolved.parent.stat()
    except OSError:
        raise ValueError("local TTS executable is unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or not info.st_mode & 0o111
        or info.st_size <= 0
        or info.st_size > _MAX_EXECUTABLE_BYTES
        or parent.st_mode & 0o022
    ):
        raise ValueError("local TTS executable is not trusted")
    return str(resolved), _hash_file(resolved, _MAX_EXECUTABLE_BYTES)


def _private_directory(value: str) -> Path:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("local TTS output directory is unavailable") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.resolve() != path
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("local TTS output directory is not private")
    return path


def _private_db_path(value: str) -> str:
    path = Path(value)
    try:
        parent = path.parent.lstat()
    except OSError:
        raise ValueError("local TTS database parent is unavailable") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
        or path.parent.resolve() != path.parent or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise ValueError("local TTS database parent is not private")
    return str(path)


def _private_file_digest(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise LocalTTSError("local TTS output is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1
            or not 44 <= info.st_size <= _MAX_AUDIO_BYTES
        ):
            raise LocalTTSError("local TTS output is not private and bounded")
        header = os.read(descriptor, 12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise LocalTTSError("local TTS output is not WAV")
        digest = hashlib.sha256(header)
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _make_private_regular(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise LocalTTSError("local TTS pending output is unavailable") from None
    if (
        path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
        or info.st_nlink != 1 or not 44 <= info.st_size <= _MAX_AUDIO_BYTES
    ):
        raise LocalTTSError("local TTS pending output is unsafe")
    os.chmod(path, 0o600, follow_symlinks=False)


def _hash_file(path: Path, maximum: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            total += len(chunk)
            if total > maximum:
                raise ValueError("local TTS executable exceeds its byte ceiling")
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local TTS timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "LocalSpeechRequest", "LocalTTSAdapter", "LocalTTSArtifact", "LocalTTSConfig", "LocalTTSError",
    "LocalTTSOutcomeUnknown",
]
