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

import duckdb

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .chapter_tts_production import PreparedChapterTTSRequest
from .documentary_production import reopen_ken_burns_documentary
from .educational_video_production import (
    EducationalVideoProductionArtifact,
    produce_educational_video,
)
from .educational_video_receipt import (
    EducationalVideoReceipt,
    receipt_file_path,
)
from .educational_video_receipt import (
    issue as issue_educational_video_receipt,
)
from .local_narration_bridge import (
    LocalNarrationInputs,
    LocalTTSArtifactResolver,
    compile_local_narration_inputs,
)
from .local_video_bridge import (
    LocalSourceCardInput,
    LocalSourceCardResolver,
    LocalVideoInputs,
    compile_local_video_inputs,
)
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .narration_production import (
    NarrationProductionArtifact,
    produce_narration_track,
)
from .production_registration import (
    MultimediaProductionRegistrationRequest,
    register_multimedia_production,
)
from .read_model import MultimediaAssetStore, MultimediaProductionLink
from .verified_playback import VerifiedPlaybackRuntime
from .visual_selection import EvidenceVerifier

DatabaseRow = tuple[object, ...]

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

_VIDEO_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_video_runs (
 run_id TEXT PRIMARY KEY, narration_run_id TEXT NOT NULL, owner_digest TEXT NOT NULL,
 asset_id TEXT NOT NULL, revision_id TEXT NOT NULL, input_digest TEXT NOT NULL,
 config_digest TEXT NOT NULL, status TEXT NOT NULL, render_manifest_path TEXT NOT NULL,
 render_manifest_sha256 TEXT NOT NULL, receipt_path TEXT NOT NULL,
 receipt_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 row_mac TEXT NOT NULL)
"""
_NARRATION_ROW_COLUMNS = 12
_VIDEO_ROW_COLUMNS = 15


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


@dataclass(frozen=True)
class LocalVideoRunRequest:
    narration: LocalNarrationRunRequest
    source_cards: tuple[LocalSourceCardInput, ...]


@dataclass(frozen=True)
class LocalVideoRunArtifact:
    run_id: str
    narration_run_id: str
    owner_digest: str
    input_digest: str
    config_digest: str
    receipt: EducationalVideoReceipt
    cost_usd: float = 0.0
    registered: bool = False


@dataclass(frozen=True)
class VideoAuthority:
    """Immutable internal authority over one registered video production chain."""

    narration_run_id: str
    video_run_id: str
    owner_digest: str
    asset_id: str
    revision_id: str
    narration_input_digest: str
    narration_config_digest: str
    narration_artifact_digest: str
    narration_updated_at: str
    video_input_digest: str
    video_config_digest: str
    video_artifact_digest: str
    receipt_digest: str
    video_updated_at: str
    receipt: EducationalVideoReceipt
    production_link: MultimediaProductionLink


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
        ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
        ffprobe_path: str = DEFAULT_FFPROBE_PATH,
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
        self, row: DatabaseRow, request: LocalNarrationRunRequest, inputs: LocalNarrationInputs,
        owner_digest: str,
    ) -> LocalNarrationRunArtifact:
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

    def _verify_row(
        self, row: DatabaseRow, request: LocalNarrationRunRequest,
        inputs: LocalNarrationInputs, owner_digest: str,
    ) -> None:
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

    def _load(self, run_id: str) -> DatabaseRow | None:
        if not Path(self._db_path).exists():
            return None
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_production_runs WHERE run_id=?", [run_id]
                ).fetchone()
        except duckdb.CatalogException:
            return None
        except Exception as exc:
            raise LocalProductionCoordinatorError(
                "local production database is unavailable"
            ) from exc


class LocalVideoProductionCoordinator:
    """Compose attested local visuals, render, and canonical receipt durably."""

    def __init__(
        self,
        *,
        narration_coordinator: LocalProductionCoordinator,
        source_card_resolver: LocalSourceCardResolver,
        verify_evidence: EvidenceVerifier,
        visual_output_dir: str,
        render_output_dir: str,
        receipt_output_dir: str,
        visual_integrity_key: bytes,
        evidence_authority_key: bytes,
        render_integrity_key: bytes,
        receipt_integrity_key: bytes,
        width_px: int = 1280,
        height_px: int = 720,
        fps: int = 30,
    ) -> None:
        keys = (
            visual_integrity_key, evidence_authority_key,
            render_integrity_key, receipt_integrity_key,
        )
        if any(not isinstance(key, bytes) or len(key) < 32 for key in keys):
            raise ValueError("local video integrity configuration is invalid")
        if width_px != 1280 or height_px != 720 or fps != 30:
            raise ValueError("local video render shape must be 1280x720 at 30 fps")
        self._narration = narration_coordinator
        self._cards = source_card_resolver
        self._verify_evidence = verify_evidence
        self._visual_root = _private_directory(visual_output_dir)
        self._render_root = _private_directory(render_output_dir)
        self._receipt_root = _private_directory(receipt_output_dir)
        self._visual_key = visual_integrity_key
        self._evidence_key = evidence_authority_key
        self._render_key = render_integrity_key
        self._receipt_key = receipt_integrity_key
        self._width = width_px
        self._height = height_px
        self._fps = fps
        self._config_digest = hashlib.sha256(
            _canonical(
                {
                    "evidence_key_identity": self._key_identity(evidence_authority_key),
                    "fps": fps,
                    "height_px": height_px,
                    "receipt_key_identity": self._key_identity(receipt_integrity_key),
                    "receipt_root": str(self._receipt_root),
                    "render_key_identity": self._key_identity(render_integrity_key),
                    "render_root": str(self._render_root),
                    "schema_version": "antiek.local-video-production-config.v1",
                    "visual_key_identity": self._key_identity(visual_integrity_key),
                    "visual_root": str(self._visual_root),
                    "width_px": width_px,
                }
            )
        ).hexdigest()

    def assert_independent_snapshot_key(self, snapshot_key: bytes) -> None:
        """Reject reuse of any key that authenticates the local video chain."""
        keys = (
            self._narration._key,
            self._narration._narration_key,
            self._visual_key,
            self._evidence_key,
            self._render_key,
            self._receipt_key,
        )
        if not isinstance(snapshot_key, bytes) or len(snapshot_key) < 32:
            raise ValueError("local zero snapshot key is invalid")
        if any(hmac.compare_digest(snapshot_key, key) for key in keys):
            raise ValueError("local zero snapshot key must be independent")

    def produce(
        self, request: LocalVideoRunRequest, *, now: datetime
    ) -> LocalVideoRunArtifact:
        narration_run = self._narration.produce_narration(request.narration, now=now)
        inputs, owner_digest = self._narration._inputs(request.narration)
        video = self._video_inputs(request, inputs, narration_run.narration)
        run_id = _video_run_id(
            narration_run.run_id, owner_digest, video.input_digest, self._config_digest
        )
        existing = self._load(run_id)
        if existing is not None:
            return self._resume_existing(
                existing, request, narration_run, inputs, video, owner_digest, now
            )
        timestamp = _timestamp(now)
        values: list[object] = [
            run_id, narration_run.run_id, owner_digest, request.narration.asset_id,
            request.narration.expected_revision_id, video.input_digest,
            self._config_digest, "rendering", str(self._render_manifest_path(request)),
            "", receipt_file_path(
                str(self._receipt_root), request.narration.asset_id,
                request.narration.expected_revision_id,
            ), "", timestamp, timestamp,
        ]
        coordinator = FlockWriteCoordinator(self._narration._db_path)
        with coordinator.acquire_write_context("multimedia.local_video.begin") as connection:
            connection.execute(_VIDEO_DDL)
            prior = connection.execute(
                "SELECT * FROM multimedia_local_video_runs WHERE run_id=?", [run_id]
            ).fetchone()
            if prior is not None:
                return self._resume_existing(
                    prior, request, narration_run, inputs, video, owner_digest, now
                )
            connection.execute(
                "INSERT INTO multimedia_local_video_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [*values, _mac(values, self._narration._key)],
            )
        try:
            production = self._produce(request, narration_run.narration, video)
            row = self._complete_render(values, production, request, video, owner_digest)
            return self._issue(row, request, narration_run, inputs, video, owner_digest, now)
        except LocalProductionOutcomeUnknown:
            raise
        except Exception as exc:
            raise LocalProductionOutcomeUnknown(
                "local video production outcome requires explicit recovery"
            ) from exc

    def recover(
        self, request: LocalVideoRunRequest, *, now: datetime
    ) -> LocalVideoRunArtifact:
        narration_run = self._narration.recover_narration(request.narration, now=now)
        inputs, owner_digest = self._narration._inputs(request.narration)
        video = self._video_inputs(request, inputs, narration_run.narration)
        run_id = _video_run_id(
            narration_run.run_id, owner_digest, video.input_digest, self._config_digest
        )
        row = self._load(run_id)
        if row is None:
            raise LocalProductionCoordinatorError("local video run is unavailable")
        self._verify_row(row, request, narration_run, video, owner_digest)
        return self._resume_existing(
            row, request, narration_run, inputs, video, owner_digest, now, recovering=True
        )

    def register(
        self, request: LocalVideoRunRequest, *, now: datetime
    ) -> LocalVideoRunArtifact:
        """Verify bounded playback and idempotently attach the exact current revision."""
        artifact = self.produce(request, now=now)
        playback = VerifiedPlaybackRuntime(
            receipt_root=str(self._receipt_root),
            receipt_key=self._receipt_key,
            narration_key=self._narration._narration_key,
            visual_key=self._visual_key,
            render_key=self._render_key,
        )
        metadata = playback.metadata(
            asset_id=request.narration.asset_id,
            revision_id=request.narration.expected_revision_id,
        )
        for kind in ("video", "audio"):
            media = playback.read(
                asset_id=request.narration.asset_id,
                revision_id=request.narration.expected_revision_id,
                kind=kind,
                range_header="bytes=0-1023",
            )
            if media.start != 0 or media.end < 0 or media.total <= 0 or not media.payload:
                raise LocalProductionCoordinatorError("local verified playback is unavailable")
        if (
            metadata.receipt_sha256
            != hashlib.sha256(artifact.receipt.to_json().encode()).hexdigest()
        ):
            raise LocalProductionCoordinatorError("local playback receipt identity conflicts")
        register_multimedia_production(
            request.narration.asset_id,
            MultimediaProductionRegistrationRequest(
                expected_revision_id=request.narration.expected_revision_id
            ),
            owner_id=request.narration.owner_id,
            store=self._narration._store,
            playback=playback,
        )
        row = self._load(artifact.run_id)
        if row is None:
            raise LocalProductionCoordinatorError("local video run is unavailable")
        if row[7] == "registered":
            return artifact
        if row[7] != "succeeded":
            raise LocalProductionCoordinatorError("local video registration state conflicts")
        updated = list(row[:14])
        updated[7] = "registered"
        updated[13] = _timestamp(now)
        self._transition(row, updated, "multimedia.local_video.register")
        return artifact.__class__(
            run_id=artifact.run_id,
            narration_run_id=artifact.narration_run_id,
            owner_digest=artifact.owner_digest,
            input_digest=artifact.input_digest,
            config_digest=artifact.config_digest,
            receipt=artifact.receipt,
            registered=True,
        )

    def registered_video_authority(
        self, owner_id: str, asset_id: str, revision_id: str
    ) -> VideoAuthority:
        """Discover the one registered video row and verify the full chain.

        Raises :class:`LocalProductionCoordinatorError` with
        ``evidence_unavailable`` when the row is missing or in a nonterminal
        state, and ``evidence_conflict`` when any verification fails.
        """
        self._narration._verify_executables()
        try:
            record = self._narration._store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalProductionCoordinatorError(
                "video authority asset is unavailable: evidence_unavailable"
            ) from exc
        asset = record.asset
        if (
            asset.revision_id != revision_id
            or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest"
            or record.mode == "audio"
            or str(asset.kind) == "audio_experience"
        ):
            raise LocalProductionCoordinatorError(
                "video authority requires the current ready cheapest video revision"
            )
        owner_digest = str(asset.owner_user_id)
        row = self._find_registered_row(owner_digest, asset_id, revision_id)
        if len(row) != _VIDEO_ROW_COLUMNS:
            raise LocalProductionCoordinatorError(
                "video authority row shape is unsupported: evidence_unavailable"
            )
        narration_run_id = str(row[1])
        video_run_id = str(row[0])
        self._verify_row_mac(row)
        expected_id = _video_run_id(
            narration_run_id, owner_digest, str(row[5]), self._config_digest
        )
        if video_run_id != expected_id or str(row[6]) != self._config_digest:
            raise LocalProductionCoordinatorError(
                "video authority deterministic identity failed"
            )
        narration_row = self._narration._load(narration_run_id)
        if narration_row is None or len(narration_row) != _NARRATION_ROW_COLUMNS:
            raise LocalProductionCoordinatorError(
                "video authority referenced narration row is missing"
            )
        if str(narration_row[6]) != "narration_succeeded":
            raise LocalProductionCoordinatorError(
                "video authority referenced narration is not terminal"
            )
        if (
            not isinstance(narration_row[11], str)
            or not hmac.compare_digest(
                narration_row[11], _mac(list(narration_row[:11]), self._narration._key)
            )
        ):
            raise LocalProductionCoordinatorError(
                "video authority narration row MAC failed"
            )
        expected_narr_run = _run_id(
            owner_digest, str(narration_row[4]), self._narration._config_digest
        )
        if (
            str(narration_row[0]) != expected_narr_run
            or str(narration_row[1]) != owner_digest
            or str(narration_row[2]) != asset_id
            or str(narration_row[3]) != revision_id
            or str(narration_row[5]) != self._narration._config_digest
        ):
            raise LocalProductionCoordinatorError(
                "video authority narration identity failed"
            )
        receipt_path = Path(str(row[10]))
        receipt_payload = _read_private(receipt_path)
        if not hmac.compare_digest(
            hashlib.sha256(receipt_payload).hexdigest(), str(row[11])
        ):
            raise LocalProductionCoordinatorError(
                "video authority receipt file digest failed"
            )
        receipt = EducationalVideoReceipt.reopen_from_file(
            str(receipt_path),
            self._receipt_key,
            self._narration._narration_key,
            self._visual_key,
            self._render_key,
        )
        if receipt.asset_id != asset_id or receipt.revision_id != revision_id:
            raise LocalProductionCoordinatorError(
                "video authority receipt identity failed"
            )
        narration_path = Path(str(narration_row[7]))
        narration_payload = _read_private(narration_path)
        render_path = Path(str(row[8]))
        render_payload = _read_private(render_path)
        if (
            not hmac.compare_digest(
                hashlib.sha256(narration_payload).hexdigest(), str(narration_row[8])
            )
            or narration_payload != receipt.narration.to_json().encode()
            or not hmac.compare_digest(
                hashlib.sha256(render_payload).hexdigest(), str(row[9])
            )
            or render_payload != receipt.render.to_json().encode()
        ):
            raise LocalProductionCoordinatorError(
                "video authority production manifests conflict"
            )
        if record.production_link is None:
            raise LocalProductionCoordinatorError(
                "video authority production link is missing"
            )
        link = record.production_link
        if (
            link.owner_identity_digest != owner_digest
            or link.asset_id != asset_id
            or link.revision_id != revision_id
            or link.receipt_sha256 != str(row[11])
        ):
            raise LocalProductionCoordinatorError(
                "video authority link identity failed"
            )
        render = receipt.render.manifest
        narration = receipt.narration.manifest
        expected_video_sha = render.output_sha256
        expected_audio_sha = narration.output_sha256
        if (
            link.video_sha256 != expected_video_sha
            or link.audio_sha256 != expected_audio_sha
            or link.chapter_ids != render.chapter_ids
            or link.duration_seconds != render.duration_seconds
            or link.width_px != render.width_px
            or link.height_px != render.height_px
        ):
            raise LocalProductionCoordinatorError(
                "video authority link receipt values failed"
            )
        fresh_video = self._load(video_run_id)
        if (
            fresh_video is None
            or len(fresh_video) != _VIDEO_ROW_COLUMNS
            or list(fresh_video[:14]) != list(row[:14])
        ):
            raise LocalProductionCoordinatorError(
                "video authority row changed during verification"
            )
        self._verify_row_mac(fresh_video)
        fresh_narr = self._narration._load(narration_run_id)
        if fresh_narr is None or list(fresh_narr) != list(narration_row):
            raise LocalProductionCoordinatorError(
                "video authority narration row changed during verification"
            )
        try:
            fresh_record = self._narration._store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalProductionCoordinatorError(
                "video authority asset disappeared during verification: evidence_conflict"
            ) from exc
        if fresh_record.production_link != link:
            raise LocalProductionCoordinatorError(
                "video authority production link changed during verification"
            )
        fresh_receipt_payload = _read_private(receipt_path)
        fresh_narration_payload = _read_private(narration_path)
        fresh_render_payload = _read_private(render_path)
        fresh_receipt = EducationalVideoReceipt.reopen_from_file(
            str(receipt_path),
            self._receipt_key,
            self._narration._narration_key,
            self._visual_key,
            self._render_key,
        )
        if (
            fresh_receipt_payload != receipt_payload
            or fresh_narration_payload != narration_payload
            or fresh_render_payload != render_payload
            or fresh_receipt != receipt
        ):
            raise LocalProductionCoordinatorError(
                "video authority files changed during verification"
            )
        return VideoAuthority(
            narration_run_id=narration_run_id,
            video_run_id=video_run_id,
            owner_digest=owner_digest,
            asset_id=asset_id,
            revision_id=revision_id,
            narration_input_digest=str(narration_row[4]),
            narration_config_digest=str(narration_row[5]),
            narration_artifact_digest=str(narration_row[8]),
            narration_updated_at=str(narration_row[10]),
            video_input_digest=str(row[5]),
            video_config_digest=str(row[6]),
            video_artifact_digest=str(row[9]),
            receipt_digest=str(row[11]),
            video_updated_at=str(row[13]),
            receipt=receipt,
            production_link=link,
        )

    def _resume_existing(
        self, row: DatabaseRow, request: LocalVideoRunRequest,
        narration_run: LocalNarrationRunArtifact, inputs: LocalNarrationInputs,
        video: LocalVideoInputs, owner_digest: str, now: datetime,
        *, recovering: bool = False,
    ) -> LocalVideoRunArtifact:
        self._verify_row(row, request, narration_run, video, owner_digest)
        if row[7] in {"succeeded", "registered"}:
            return self._reopen_receipt(row, narration_run, video, owner_digest)
        if row[7] == "rendering":
            if not recovering:
                raise LocalProductionOutcomeUnknown("local video render outcome is unknown")
            try:
                production = self._reopen_production(request, narration_run.narration, video)
            except Exception as exc:
                raise LocalProductionOutcomeUnknown("local video render output is unavailable") from exc
            row = self._complete_render(
                list(row[:14]), production, request, video, owner_digest
            )
        if row[7] in {"render_succeeded", "receipting"}:
            return self._issue(
                row, request, narration_run, inputs, video, owner_digest, now,
                recovering=recovering,
            )
        raise LocalProductionCoordinatorError("local video production state conflicts")

    def _produce(
        self, request: LocalVideoRunRequest, narration: NarrationProductionArtifact,
        video: LocalVideoInputs,
    ) -> EducationalVideoProductionArtifact:
        return produce_educational_video(
            asset_id=request.narration.asset_id,
            revision_id=request.narration.expected_revision_id,
            narration=narration,
            narration_integrity_key=self._narration._narration_key,
            timeline=video.timeline,
            selections=video.selections,
            visual_output_dir=str(self._visual_root),
            render_output_dir=str(self._render_root),
            visual_integrity_key=self._visual_key,
            evidence_authority_key=self._evidence_key,
            render_integrity_key=self._render_key,
            verify_evidence=self._verify_evidence,
            ffmpeg_path=self._narration._ffmpeg,
            ffprobe_path=self._narration._ffprobe,
            width_px=self._width, height_px=self._height, fps=self._fps,
            timeout_seconds=self._narration._timeout,
        )

    def _reopen_production(
        self, request: LocalVideoRunRequest, narration: NarrationProductionArtifact,
        video: LocalVideoInputs,
    ) -> EducationalVideoProductionArtifact:
        documentary = reopen_ken_burns_documentary(
            asset_id=request.narration.asset_id,
            revision_id=request.narration.expected_revision_id,
            timeline=video.timeline,
            narration_path=narration.manifest.output_path,
            visual_output_dir=str(self._visual_root),
            render_output_dir=str(self._render_root),
            visual_integrity_key=self._visual_key,
            render_integrity_key=self._render_key,
            width_px=self._width, height_px=self._height, fps=self._fps,
        )
        return EducationalVideoProductionArtifact(narration=narration, documentary=documentary)

    def _complete_render(
        self, prior_values: list[object], production: EducationalVideoProductionArtifact,
        request: LocalVideoRunRequest, video: LocalVideoInputs, owner_digest: str,
    ) -> tuple[object, ...]:
        reopened = self._reopen_production(request, production.narration, video)
        if reopened != production:
            raise LocalProductionCoordinatorError("local video render conflicts")
        path = self._render_manifest_path(request)
        digest = hashlib.sha256(_read_private(path)).hexdigest()
        completed = [*prior_values]
        completed[7] = "render_succeeded"
        completed[8] = str(path)
        completed[9] = digest
        coordinator = FlockWriteCoordinator(self._narration._db_path)
        with coordinator.acquire_write_context("multimedia.local_video.render") as connection:
            current = connection.execute(
                "SELECT * FROM multimedia_local_video_runs WHERE run_id=?", [completed[0]]
            ).fetchone()
            self._verify_row_base(current, list(prior_values))
            if current[7] == "render_succeeded":
                return tuple(current)
            if current[7] != "rendering":
                raise LocalProductionCoordinatorError("local video render state conflicts")
            connection.execute(
                "UPDATE multimedia_local_video_runs SET status=?, render_manifest_path=?, "
                "render_manifest_sha256=?, row_mac=? WHERE run_id=?",
                [completed[7], completed[8], completed[9],
                 _mac(completed, self._narration._key), completed[0]],
            )
        return tuple([*completed, _mac(completed, self._narration._key)])

    def _issue(
        self, row: DatabaseRow, request: LocalVideoRunRequest, narration_run: LocalNarrationRunArtifact,
        inputs: LocalNarrationInputs, video: LocalVideoInputs, owner_digest: str,
        now: datetime, *, recovering: bool = False,
    ) -> LocalVideoRunArtifact:
        self._verify_row(row, request, narration_run, video, owner_digest)
        production = self._reopen_production(request, narration_run.narration, video)
        current = row
        if row[7] == "render_succeeded":
            started = list(row[:14])
            started[7] = "receipting"
            started[13] = _timestamp(now)
            current = self._transition(row, started, "multimedia.local_video.receipting")
        elif row[7] == "receipting" and not recovering:
            raise LocalProductionOutcomeUnknown("local video receipt outcome is unknown")
        try:
            receipt = issue_educational_video_receipt(
                artifact=production,
                receipt_key=self._receipt_key,
                narration_key=self._narration._narration_key,
                visual_key=self._visual_key,
                render_key=self._render_key,
                output_dir=str(self._receipt_root),
            )
        except Exception as exc:
            raise LocalProductionOutcomeUnknown("local video receipt output is unknown") from exc
        path = Path(str(current[10]))
        payload = _read_private(path)
        reopened = EducationalVideoReceipt.reopen_from_file(
            str(path), self._receipt_key, self._narration._narration_key,
            self._visual_key, self._render_key,
        )
        if reopened != receipt:
            raise LocalProductionCoordinatorError("local video receipt conflicts")
        completed = list(current[:14])
        completed[7] = "succeeded"
        completed[11] = hashlib.sha256(payload).hexdigest()
        completed[13] = _timestamp(now)
        final = self._transition(current, completed, "multimedia.local_video.complete")
        return self._reopen_receipt(final, narration_run, video, owner_digest)

    def _transition(
        self, current: DatabaseRow, updated: list[object], operation: str
    ) -> DatabaseRow:
        coordinator = FlockWriteCoordinator(self._narration._db_path)
        with coordinator.acquire_write_context(operation) as connection:
            stored = connection.execute(
                "SELECT * FROM multimedia_local_video_runs WHERE run_id=?", [updated[0]]
            ).fetchone()
            self._verify_row_base(stored, list(current[:14]))
            if stored[7] == updated[7] and list(stored[:14]) == updated:
                return tuple(stored)
            connection.execute(
                "UPDATE multimedia_local_video_runs SET status=?, receipt_sha256=?, "
                "updated_at=?, row_mac=? WHERE run_id=?",
                [updated[7], updated[11], updated[13],
                 _mac(updated, self._narration._key), updated[0]],
            )
        return tuple([*updated, _mac(updated, self._narration._key)])

    def _reopen_receipt(
        self, row: DatabaseRow, narration_run: LocalNarrationRunArtifact,
        video: LocalVideoInputs, owner_digest: str,
    ) -> LocalVideoRunArtifact:
        path = Path(str(row[10]))
        payload = _read_private(path)
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), str(row[11])):
            raise LocalProductionCoordinatorError("local video receipt digest conflicts")
        receipt = EducationalVideoReceipt.reopen_from_file(
            str(path), self._receipt_key, self._narration._narration_key,
            self._visual_key, self._render_key,
        )
        return LocalVideoRunArtifact(
            run_id=str(row[0]), narration_run_id=narration_run.run_id,
            owner_digest=owner_digest, input_digest=video.input_digest,
            config_digest=self._config_digest, receipt=receipt,
            registered=row[7] == "registered",
        )

    def _video_inputs(
        self, request: LocalVideoRunRequest, inputs: LocalNarrationInputs,
        narration: NarrationProductionArtifact,
    ) -> LocalVideoInputs:
        record = self._narration._store.get(
            request.narration.asset_id, owner_id=request.narration.owner_id
        )
        return compile_local_video_inputs(
            record.plan, inputs, narration, request.source_cards,
            owner_id=request.narration.owner_id, resolver=self._cards,
            verify_evidence=self._verify_evidence,
        )

    def _verify_row(
        self, row: DatabaseRow, request: LocalVideoRunRequest,
        narration_run: LocalNarrationRunArtifact, video: LocalVideoInputs,
        owner_digest: str,
    ) -> None:
        expected = [
            _video_run_id(narration_run.run_id, owner_digest, video.input_digest, self._config_digest),
            narration_run.run_id, owner_digest, request.narration.asset_id,
            request.narration.expected_revision_id, video.input_digest, self._config_digest,
        ]
        if row is None or len(row) != 15 or list(row[:7]) != expected:
            raise LocalProductionCoordinatorError("stored local video integrity failed")
        self._verify_row_mac(row)

    def _verify_row_base(self, row: DatabaseRow, expected: list[object]) -> None:
        if (
            row is None or len(row) != 15 or list(row[:14]) != expected
        ):
            raise LocalProductionCoordinatorError("stored local video integrity failed")
        self._verify_row_mac(row)

    def _verify_row_mac(self, row: DatabaseRow) -> None:
        if (
            not isinstance(row[14], str)
            or not hmac.compare_digest(
                row[14], _mac(list(row[:14]), self._narration._key)
            )
        ):
            raise LocalProductionCoordinatorError("stored local video integrity failed")

    def _render_manifest_path(self, request: LocalVideoRunRequest) -> Path:
        return self._render_root / (
            f"{request.narration.asset_id}-{request.narration.expected_revision_id}"
        ) / "render.json"

    def _find_registered_row(
        self, owner_digest: str, asset_id: str, revision_id: str
    ) -> DatabaseRow:
        if not Path(self._narration._db_path).exists():
            raise LocalProductionCoordinatorError(
                "video authority database is unavailable: evidence_unavailable"
            )
        try:
            with connect_read(self._narration._db_path) as connection:
                try:
                    rows = connection.execute(
                        "SELECT * FROM multimedia_local_video_runs "
                        "WHERE owner_digest=? AND asset_id=? AND revision_id=? "
                        "AND status='registered'",
                        [owner_digest, asset_id, revision_id],
                    ).fetchall()
                except duckdb.CatalogException:
                    raise LocalProductionCoordinatorError(
                        "video authority table is missing: evidence_unavailable"
                    ) from None
        except LocalProductionCoordinatorError:
            raise
        except Exception as exc:
            raise LocalProductionCoordinatorError(
                "video authority database is unavailable: evidence_unavailable"
            ) from exc
        if len(rows) == 0:
            raise LocalProductionCoordinatorError(
                "video authority registered row is missing: evidence_unavailable"
            )
        if len(rows) > 1:
            raise LocalProductionCoordinatorError(
                "video authority has multiple registered rows: evidence_unavailable"
            )
        return rows[0]

    def _load(self, run_id: str) -> DatabaseRow | None:
        if not Path(self._narration._db_path).exists():
            return None
        try:
            with connect_read(self._narration._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_video_runs WHERE run_id=?", [run_id]
                ).fetchone()
        except duckdb.CatalogException:
            return None
        except Exception as exc:
            raise LocalProductionCoordinatorError(
                "local production database is unavailable"
            ) from exc

    def _key_identity(self, key: bytes) -> str:
        return hmac.new(self._narration._key, key, hashlib.sha256).hexdigest()


def _run_id(owner_digest: str, input_digest: str, config_digest: str) -> str:
    return "mmlocalrun_" + hashlib.sha256(
        f"{owner_digest}\0{input_digest}\0{config_digest}".encode()
    ).hexdigest()


def _video_run_id(
    narration_run_id: str, owner_digest: str, input_digest: str, config_digest: str
) -> str:
    return "mmlocalvideo_" + hashlib.sha256(
        f"{narration_run_id}\0{owner_digest}\0{input_digest}\0{config_digest}".encode()
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
    "LocalVideoProductionCoordinator",
    "LocalVideoRunArtifact",
    "LocalVideoRunRequest",
    "VideoAuthority",
]
