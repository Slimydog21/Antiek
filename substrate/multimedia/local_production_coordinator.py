"""Durable zero-network orchestration for cheapest local multimedia production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .chapter_tts_production import PreparedChapterTTSRequest
from .local_narration_bridge import (
    LocalNarrationInputs,
    LocalTTSArtifactResolver,
    compile_local_narration_inputs,
)
from .narration_production import (
    NarrationProductionArtifact,
    produce_narration_track,
)
from .read_model import MultimediaAssetStore

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_production_runs (
 run_id TEXT PRIMARY KEY, owner_digest TEXT NOT NULL, asset_id TEXT NOT NULL,
 revision_id TEXT NOT NULL, input_digest TEXT NOT NULL, config_digest TEXT NOT NULL,
 status TEXT NOT NULL, narration_manifest_path TEXT NOT NULL,
 narration_manifest_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, row_mac TEXT NOT NULL)
"""


class LocalProductionCoordinatorError(RuntimeError):
    """A local production run failed an authority or state check."""


class LocalProductionOutcomeUnknown(LocalProductionCoordinatorError):
    """An external local process may have completed and requires recovery."""


@dataclass(frozen=True)
class LocalNarrationRunRequest:
    owner_id: str
    asset_id: str
    expected_revision_id: str
    chapter_requests: tuple[PreparedChapterTTSRequest, ...]


@dataclass(frozen=True)
class LocalNarrationRunArtifact:
    run_id: str
    owner_digest: str
    asset_id: str
    revision_id: str
    input_digest: str
    config_digest: str
    narration: NarrationProductionArtifact
    cost_usd: float = 0.0


class LocalProductionCoordinator:
    """Own narration phase execution and explicit unknown-outcome adoption."""

    def __init__(
        self,
        *,
        db_path: str,
        signing_key: bytes,
        narration_integrity_key: bytes,
        narration_output_dir: str,
        store: MultimediaAssetStore,
        tts_resolver: LocalTTSArtifactResolver,
        ffmpeg_path: str = "/opt/homebrew/bin/ffmpeg",
        ffprobe_path: str = "/opt/homebrew/bin/ffprobe",
        timeout_seconds: int = 300,
    ) -> None:
        if (
            not isinstance(signing_key, bytes)
            or len(signing_key) < 32
            or not isinstance(narration_integrity_key, bytes)
            or len(narration_integrity_key) < 32
            or not 1 <= timeout_seconds <= 900
        ):
            raise ValueError("local production coordinator configuration is invalid")
        self._db_path = _private_db_path(db_path)
        self._key = signing_key
        self._narration_key = narration_integrity_key
        self._root = _private_directory(narration_output_dir)
        self._store = store
        self._resolver = tts_resolver
        self._ffmpeg, ffmpeg_digest = _executable(ffmpeg_path)
        self._ffprobe, ffprobe_digest = _executable(ffprobe_path)
        self._ffmpeg_digest = ffmpeg_digest
        self._ffprobe_digest = ffprobe_digest
        self._timeout = timeout_seconds
        self._config_digest = hashlib.sha256(
            _canonical(
                {
                    "ffmpeg_digest": ffmpeg_digest,
                    "ffprobe_digest": ffprobe_digest,
                    "narration_key_identity": hmac.new(
                        signing_key, narration_integrity_key, hashlib.sha256
                    ).hexdigest(),
                    "output_root": str(self._root),
                    "schema_version": "antiek.local-production-config.v1",
                    "timeout_seconds": timeout_seconds,
                }
            )
        ).hexdigest()

    def produce_narration(
        self, request: LocalNarrationRunRequest, *, now: datetime
    ) -> LocalNarrationRunArtifact:
        inputs, owner_digest = self._inputs(request)
        run_id = _run_id(owner_digest, inputs.input_digest, self._config_digest)
        existing = self._load(run_id)
        if existing is not None:
            return self._reopen_row(existing, request, inputs, owner_digest)
        timestamp = _timestamp(now)
        manifest_path = self._manifest_path(request.asset_id, request.expected_revision_id)
        values: list[object] = [
            run_id, owner_digest, request.asset_id, request.expected_revision_id,
            inputs.input_digest, self._config_digest, "producing", str(manifest_path),
            "", timestamp, timestamp,
        ]
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_production.begin") as connection:
            connection.execute(_DDL)
            prior = connection.execute(
                "SELECT * FROM multimedia_local_production_runs WHERE run_id=?", [run_id]
            ).fetchone()
            if prior is not None:
                return self._reopen_row(prior, request, inputs, owner_digest)
            connection.execute(
                "INSERT INTO multimedia_local_production_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [*values, _mac(values, self._key)],
            )
        try:
            narration = produce_narration_track(
                asset_id=inputs.asset_id,
                revision_id=inputs.revision_id,
                chapters=inputs.chapters,
                generated_files=inputs.generated_files,
                chapter_paths=inputs.chapter_paths,
                output_dir=str(self._root),
                integrity_key=self._narration_key,
                ffmpeg_path=self._ffmpeg,
                ffprobe_path=self._ffprobe,
                sample_rate_hz=request.chapter_requests[0].sample_rate_hz,
                channels=request.chapter_requests[0].channels,
                timeout_seconds=self._timeout,
            )
            self._verify_narration(narration, inputs)
            return self._complete(values, narration, request, inputs, owner_digest)
        except LocalProductionOutcomeUnknown:
            raise
        except Exception as exc:
            raise LocalProductionOutcomeUnknown(
                "local narration production outcome requires explicit recovery"
            ) from exc

    def recover_narration(
        self, request: LocalNarrationRunRequest, *, now: datetime
    ) -> LocalNarrationRunArtifact:
        inputs, owner_digest = self._inputs(request)
        run_id = _run_id(owner_digest, inputs.input_digest, self._config_digest)
        row = self._load(run_id)
        if row is None:
            raise LocalProductionCoordinatorError("local production run is unavailable")
        self._verify_row(row, request, inputs, owner_digest)
        if row[6] == "narration_succeeded":
            return self._reopen_row(row, request, inputs, owner_digest)
        if row[6] != "producing":
            raise LocalProductionCoordinatorError("local production state cannot be recovered")
        path = Path(str(row[7]))
        if not path.exists() or path.is_symlink():
            raise LocalProductionOutcomeUnknown("local narration output is unavailable")
        narration = NarrationProductionArtifact.reopen(
            _read_private(path), self._narration_key
        )
        self._verify_narration(narration, inputs)
        values = list(row[:11])
        values[10] = _timestamp(now)
        return self._complete(values, narration, request, inputs, owner_digest)

    def _inputs(
        self, request: LocalNarrationRunRequest
    ) -> tuple[LocalNarrationInputs, str]:
        self._verify_executables()
        if not isinstance(request, LocalNarrationRunRequest) or not request.owner_id:
            raise ValueError("local production request is invalid")
        try:
            record = self._store.get(request.asset_id, owner_id=request.owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalProductionCoordinatorError("multimedia asset is unavailable") from exc
        asset = record.asset
        if (
            asset.revision_id != request.expected_revision_id
            or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest"
            or record.mode == "audio"
            or str(asset.kind) == "audio_experience"
        ):
            raise LocalProductionCoordinatorError(
                "local production requires the current ready cheapest video revision"
            )
        inputs = compile_local_narration_inputs(
            record.plan, request.chapter_requests, resolver=self._resolver
        )
        if inputs.asset_id != asset.asset_id or inputs.revision_id != asset.revision_id:
            raise LocalProductionCoordinatorError("local narration identity conflicts with asset")
        return inputs, str(asset.owner_user_id)

    def _verify_executables(self) -> None:
        ffmpeg, ffmpeg_digest = _executable(self._ffmpeg)
        ffprobe, ffprobe_digest = _executable(self._ffprobe)
        if (
            ffmpeg != self._ffmpeg
            or ffprobe != self._ffprobe
            or not hmac.compare_digest(ffmpeg_digest, self._ffmpeg_digest)
            or not hmac.compare_digest(ffprobe_digest, self._ffprobe_digest)
        ):
            raise LocalProductionCoordinatorError(
                "local production executable identity changed"
            )

    def _complete(
        self,
        prior_values: list[object],
        narration: NarrationProductionArtifact,
        request: LocalNarrationRunRequest,
        inputs: LocalNarrationInputs,
        owner_digest: str,
    ) -> LocalNarrationRunArtifact:
        path = self._manifest_path(request.asset_id, request.expected_revision_id)
        payload = _read_private(path)
        reopened = NarrationProductionArtifact.reopen(payload, self._narration_key)
        if reopened != narration:
            raise LocalProductionCoordinatorError("local narration manifest conflicts")
        digest = hashlib.sha256(payload).hexdigest()
        completed = [*prior_values]
        completed[6] = "narration_succeeded"
        completed[7] = str(path)
        completed[8] = digest
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_production.narration") as connection:
            connection.execute(_DDL)
            current = connection.execute(
                "SELECT * FROM multimedia_local_production_runs WHERE run_id=?",
                [prior_values[0]],
            ).fetchone()
            self._verify_row(current, request, inputs, owner_digest)
            if current[6] == "narration_succeeded":
                return self._reopen_row(current, request, inputs, owner_digest)
            if current[6] != "producing":
                raise LocalProductionCoordinatorError("local production state conflicts")
            connection.execute(
                "UPDATE multimedia_local_production_runs SET status=?, "
                "narration_manifest_path=?, narration_manifest_sha256=?, updated_at=?, "
                "row_mac=? WHERE run_id=?",
                [completed[6], completed[7], completed[8], completed[10],
                 _mac(completed, self._key), completed[0]],
            )
        return LocalNarrationRunArtifact(
            run_id=str(completed[0]), owner_digest=owner_digest,
            asset_id=inputs.asset_id, revision_id=inputs.revision_id,
            input_digest=inputs.input_digest, config_digest=self._config_digest,
            narration=reopened,
        )

    def _reopen_row(
        self, row, request: LocalNarrationRunRequest, inputs: LocalNarrationInputs,
        owner_digest: str,
    ) -> LocalNarrationRunArtifact:  # noqa: ANN001
        self._verify_row(row, request, inputs, owner_digest)
        if row[6] == "producing":
            raise LocalProductionOutcomeUnknown("local narration production outcome is unknown")
        if row[6] != "narration_succeeded" or not row[8]:
            raise LocalProductionCoordinatorError("local narration production is incomplete")
        payload = _read_private(Path(str(row[7])))
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), str(row[8])):
            raise LocalProductionCoordinatorError("local narration manifest digest conflicts")
        narration = NarrationProductionArtifact.reopen(payload, self._narration_key)
        self._verify_narration(narration, inputs)
        return LocalNarrationRunArtifact(
            run_id=str(row[0]), owner_digest=owner_digest, asset_id=inputs.asset_id,
            revision_id=inputs.revision_id, input_digest=inputs.input_digest,
            config_digest=self._config_digest, narration=narration,
        )

    def _verify_row(self, row, request, inputs, owner_digest) -> None:  # noqa: ANN001
        if (
            row is None or len(row) != 12
            or not isinstance(row[11], str)
            or not hmac.compare_digest(row[11], _mac(list(row[:11]), self._key))
            or row[0] != _run_id(owner_digest, inputs.input_digest, self._config_digest)
            or row[1] != owner_digest or row[2] != request.asset_id
            or row[3] != request.expected_revision_id or row[4] != inputs.input_digest
            or row[5] != self._config_digest
        ):
            raise LocalProductionCoordinatorError("stored local production integrity failed")

    def _verify_narration(
        self, artifact: NarrationProductionArtifact, inputs: LocalNarrationInputs
    ) -> None:
        manifest = artifact.manifest
        if (
            manifest.asset_id != inputs.asset_id
            or manifest.revision_id != inputs.revision_id
            or tuple(row.chapter_id for row in manifest.sources)
            != tuple(row.chapter_id for row in inputs.chapters)
            or tuple(row.audio_file_id for row in manifest.sources) != inputs.request_ids
            or tuple(row.sha256 for row in manifest.sources)
            != tuple(row.sha256 for row in inputs.generated_files)
            or tuple(row.duration_seconds for row in manifest.sources)
            != tuple(row.duration_seconds for row in inputs.generated_files)
        ):
            raise LocalProductionCoordinatorError("local narration output is not input-bound")

    def _manifest_path(self, asset_id: str, revision_id: str) -> Path:
        return self._root / f"{asset_id}-{revision_id}-narration" / "narration.json"

    def _load(self, run_id: str):  # noqa: ANN202
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_production_runs WHERE run_id=?", [run_id]
                ).fetchone()
        except Exception:
            return None


def _run_id(owner_digest: str, input_digest: str, config_digest: str) -> str:
    return "mmlocalrun_" + hashlib.sha256(
        f"{owner_digest}\0{input_digest}\0{config_digest}".encode()
    ).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local production timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _private_directory(value: str) -> Path:
    path = Path(value)
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("local production output directory is unavailable") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.resolve() != path
        or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("local production output directory is not private")
    return path


def _private_db_path(value: str) -> str:
    path = Path(value)
    try:
        parent = path.parent.lstat()
    except OSError:
        raise ValueError("local production database parent is unavailable") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
        or path.parent.resolve() != path.parent or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise ValueError("local production database parent is not private")
    return str(path)


def _executable(value: str) -> tuple[str, str]:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except OSError:
        raise ValueError("local production executable is unavailable") from None
    if (
        not path.is_absolute() or not stat.S_ISREG(info.st_mode)
        or not info.st_mode & 0o111 or not 0 < info.st_size <= _MAX_EXECUTABLE_BYTES
    ):
        raise ValueError("local production executable is invalid")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return str(resolved), digest.hexdigest()


def _read_private(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise LocalProductionCoordinatorError("local narration manifest is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not 0 < info.st_size <= _MAX_MANIFEST_BYTES
        ):
            raise LocalProductionCoordinatorError("local narration manifest is not private")
        payload = b""
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise LocalProductionCoordinatorError("local narration manifest was truncated")
            payload += chunk
            remaining -= len(chunk)
        return payload
    finally:
        os.close(descriptor)


__all__ = [
    "LocalNarrationRunArtifact",
    "LocalNarrationRunRequest",
    "LocalProductionCoordinator",
    "LocalProductionCoordinatorError",
    "LocalProductionOutcomeUnknown",
]
