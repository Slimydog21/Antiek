"""Durable orchestration for cheapest local AudibleRun production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .audible_experience_receipt import (
    AudibleExperienceReceipt,
    issue_audible_experience_receipt,
)
from .audio_production_registration import (
    MultimediaAudioRegistrationRequest,
    register_multimedia_audio_production,
)
from .local_audible_bridge import (
    LocalAudibleArtifactResolver,
    LocalAudibleInputs,
    compile_local_audible_inputs,
)
from .local_audible_production import (
    LocalAudibleProductionArtifact,
    produce_local_audible_track,
)
from .local_audible_tts import PreparedAudibleSpanTTSRequest
from .media_executables import DEFAULT_FFMPEG_PATH, DEFAULT_FFPROBE_PATH
from .read_model import MultimediaAssetStore, MultimediaAudioProductionLink
from .verified_audio_playback import VerifiedAudioPlaybackRuntime

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_audible_runs (
 run_id TEXT PRIMARY KEY, owner_digest TEXT NOT NULL, asset_id TEXT NOT NULL,
 revision_id TEXT NOT NULL, input_digest TEXT NOT NULL, config_digest TEXT NOT NULL,
 status TEXT NOT NULL, production_path TEXT NOT NULL, production_sha256 TEXT NOT NULL,
 receipt_path TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, row_mac TEXT NOT NULL)
"""

_MAX_RECEIPT_BYTES = 8 * 1024 * 1024

AudibleRunStatus = Literal[
    "producing",
    "audio_succeeded",
    "receipting",
    "succeeded",
    "registering",
    "registered",
]
DatabaseRow = tuple[object, ...]


class LocalAudibleCoordinatorError(RuntimeError):
    """Audible production authority or durable state failed closed."""


class LocalAudibleOutcomeUnknown(LocalAudibleCoordinatorError):
    """A local external boundary requires explicit recovery."""


@dataclass(frozen=True)
class LocalAudibleRunRequest:
    owner_id: str
    asset_id: str
    expected_revision_id: str
    span_requests: tuple[PreparedAudibleSpanTTSRequest, ...]


@dataclass(frozen=True)
class LocalAudibleRunResult:
    run_id: str
    input_digest: str
    receipt: AudibleExperienceReceipt
    cost_usd: float = 0.0
    registered: bool = True


@dataclass(frozen=True)
class AudibleAuthority:
    """Immutable internal authority over one registered audio production chain."""

    run_id: str
    owner_digest: str
    asset_id: str
    revision_id: str
    input_digest: str
    config_digest: str
    artifact_digest: str
    receipt_digest: str
    updated_at: str
    receipt: AudibleExperienceReceipt
    audio_production_link: MultimediaAudioProductionLink


class LocalAudibleCoordinator:
    def __init__(
        self,
        *,
        db_path: str,
        signing_key: bytes,
        production_integrity_key: bytes,
        receipt_key: bytes,
        output_dir: str,
        store: MultimediaAssetStore,
        tts_resolver: LocalAudibleArtifactResolver,
        ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
        ffprobe_path: str = DEFAULT_FFPROBE_PATH,
        timeout_seconds: int = 300,
    ) -> None:
        if (
            not isinstance(signing_key, bytes)
            or len(signing_key) < 32
            or not isinstance(production_integrity_key, bytes)
            or len(production_integrity_key) < 32
            or not isinstance(receipt_key, bytes)
            or len(receipt_key) < 32
            or not 1 <= timeout_seconds <= 900
        ):
            raise ValueError("local audible coordinator configuration is invalid")
        self._db_path = _private_db_path(db_path)
        self._key = signing_key
        self._production_key = production_integrity_key
        self._receipt_key = receipt_key
        self._root = _private_directory(output_dir)
        self._store = store
        self._resolver = tts_resolver
        self._ffmpeg, ffmpeg_digest = _trusted_executable(ffmpeg_path)
        self._ffprobe, ffprobe_digest = _trusted_executable(ffprobe_path)
        self._ffmpeg_digest = ffmpeg_digest
        self._ffprobe_digest = ffprobe_digest
        self._timeout = timeout_seconds
        self._config_digest = hashlib.sha256(
            _canonical(
                {
                    "ffmpeg_digest": ffmpeg_digest,
                    "ffprobe_digest": ffprobe_digest,
                    "output_root": str(self._root),
                    "coordinator_key_identity": hmac.new(
                        signing_key, b"local-audible-coordinator", hashlib.sha256
                    ).hexdigest(),
                    "production_key_identity": hmac.new(
                        signing_key, production_integrity_key, hashlib.sha256
                    ).hexdigest(),
                    "receipt_key_identity": hmac.new(
                        signing_key, receipt_key, hashlib.sha256
                    ).hexdigest(),
                    "schema_version": "antiek.local-audible-coordinator-config.v1",
                    "timeout_seconds": timeout_seconds,
                }
            )
        ).hexdigest()

    def assert_independent_snapshot_key(self, snapshot_key: bytes) -> None:
        """Reject reuse of any key that authenticates the local audio chain."""
        if not isinstance(snapshot_key, bytes) or len(snapshot_key) < 32:
            raise ValueError("local zero snapshot key is invalid")
        if any(
            hmac.compare_digest(snapshot_key, key)
            for key in (self._key, self._production_key, self._receipt_key)
        ):
            raise ValueError("local zero snapshot key must be independent")

    def produce(
        self, request: LocalAudibleRunRequest, *, now: datetime
    ) -> LocalAudibleRunResult:
        inputs, owner_digest = self._inputs(request)
        run_id = _run_id(owner_digest, inputs.input_digest, self._config_digest)
        existing = self._load(run_id)
        if existing is not None:
            self._verify_row(existing, request, inputs, owner_digest)
            if existing[6] == "registered":
                return self._result(existing, request, inputs, owner_digest)
            raise LocalAudibleOutcomeUnknown(
                "local audible run already exists and requires explicit recovery"
            )
        timestamp = _timestamp(now)
        production_path = self._production_manifest_path(inputs)
        receipt_path = production_path.with_name("receipt.json")
        values: list[object] = [
            run_id,
            owner_digest,
            request.asset_id,
            request.expected_revision_id,
            inputs.input_digest,
            self._config_digest,
            "producing",
            str(production_path),
            "",
            str(receipt_path),
            "",
            timestamp,
            timestamp,
        ]
        if not self._insert(values):
            raise LocalAudibleOutcomeUnknown(
                "local audible run election requires explicit recovery"
            )
        try:
            production = self._produce_track(inputs)
        except Exception as exc:
            raise LocalAudibleOutcomeUnknown(
                "local audible production outcome requires explicit recovery"
            ) from exc
        row = self._advance(
            run_id,
            expected="producing",
            status="audio_succeeded",
            production_sha256=_sha(production.to_json().encode("ascii")),
            now=now,
        )
        return self._receipt_and_register(row, request, inputs, owner_digest, production, now)

    def recover(
        self, request: LocalAudibleRunRequest, *, now: datetime
    ) -> LocalAudibleRunResult:
        inputs, owner_digest = self._inputs(request)
        run_id = _run_id(owner_digest, inputs.input_digest, self._config_digest)
        row = self._load(run_id)
        if row is None:
            raise LocalAudibleCoordinatorError("local audible run is unavailable")
        self._verify_row(row, request, inputs, owner_digest)
        status = str(row[6])
        if status == "registered":
            return self._result(row, request, inputs, owner_digest)
        try:
            if status == "producing":
                try:
                    production = self._reopen_production(Path(str(row[7])), inputs)
                except LocalAudibleCoordinatorError as exc:
                    raise LocalAudibleOutcomeUnknown(
                        "local audible production output is not yet adoptable"
                    ) from exc
                row = self._advance(
                    run_id,
                    expected="producing",
                    status="audio_succeeded",
                    production_sha256=_sha(production.to_json().encode("ascii")),
                    now=now,
                )
            else:
                production = self._reopen_production(Path(str(row[7])), inputs)
            if str(row[6]) in {"audio_succeeded", "receipting"}:
                return self._receipt_and_register(
                    row, request, inputs, owner_digest, production, now
                )
            if str(row[6]) in {"succeeded", "registering"}:
                receipt = self._reopen_receipt(Path(str(row[9])), request, inputs)
                return self._register(row, request, inputs, owner_digest, receipt, now)
        except LocalAudibleCoordinatorError:
            raise
        except Exception as exc:
            raise LocalAudibleOutcomeUnknown(
                "local audible recovery remains outcome-unknown"
            ) from exc
        raise LocalAudibleCoordinatorError("local audible run state is invalid")

    def receipt_path(self, asset_id: str, revision_id: str) -> Path:
        rows = self._rows_for_identity(asset_id, revision_id)
        eligible = [row for row in rows if str(row[6]) in {"succeeded", "registering", "registered"}]
        if len(eligible) != 1:
            raise LocalAudibleCoordinatorError("local audible receipt is unavailable")
        row = eligible[0]
        if not isinstance(row[13], str) or not hmac.compare_digest(
            row[13], _mac(list(row[:13]), self._key)
        ):
            raise LocalAudibleCoordinatorError("stored local audible integrity failed")
        return Path(str(row[9]))

    def registered_audible_authority(
        self, owner_id: str, asset_id: str, revision_id: str
    ) -> AudibleAuthority:
        """Discover the one registered audible row and verify the full chain.

        Raises :class:`LocalAudibleCoordinatorError` with
        ``evidence_unavailable`` when the row is missing or in a nonterminal
        state, and ``evidence_conflict`` when any verification fails.
        """
        self._verify_executables()
        try:
            record = self._store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalAudibleCoordinatorError(
                "audible authority asset is unavailable: evidence_unavailable"
            ) from exc
        asset = record.asset
        if (
            asset.revision_id != revision_id
            or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest"
            or record.mode != "audio"
            or str(asset.kind) != "audio_experience"
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority requires the current ready cheapest audio revision"
            )
        owner_digest = str(asset.owner_user_id)
        row = self._find_registered_row(owner_digest, asset_id, revision_id)
        if len(row) != 14:
            raise LocalAudibleCoordinatorError(
                "audible authority row shape is unsupported: evidence_unavailable"
            )
        run_id = str(row[0])
        self._verify_row_mac(row)
        expected_id = _run_id(owner_digest, str(row[4]), self._config_digest)
        if run_id != expected_id or str(row[5]) != self._config_digest:
            raise LocalAudibleCoordinatorError(
                "audible authority deterministic identity failed"
            )
        receipt_path = Path(str(row[9]))
        receipt_payload = _read_private(receipt_path, _MAX_RECEIPT_BYTES)
        if not hmac.compare_digest(
            hashlib.sha256(receipt_payload).hexdigest(), str(row[10])
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority receipt file digest failed"
            )
        receipt = AudibleExperienceReceipt.reopen_from_file(
            receipt_path,
            signing_key=self._receipt_key,
            production_integrity_key=self._production_key,
        )
        if receipt.asset_id != asset_id or receipt.revision_id != revision_id:
            raise LocalAudibleCoordinatorError(
                "audible authority receipt identity failed"
            )
        if receipt.owner_digest != owner_digest:
            raise LocalAudibleCoordinatorError(
                "audible authority receipt owner identity failed"
            )
        if receipt.production.manifest.input_digest != str(row[4]):
            raise LocalAudibleCoordinatorError(
                "audible authority production input digest failed"
            )
        production_path = Path(str(row[7]))
        production_payload = _read_private(production_path, 4 * 1024 * 1024)
        if (
            not hmac.compare_digest(_sha(production_payload), str(row[8]))
            or production_payload != receipt.production.to_json().encode("ascii")
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority production manifest conflicts"
            )
        if record.audio_production_link is None:
            raise LocalAudibleCoordinatorError(
                "audible authority audio production link is missing"
            )
        link = record.audio_production_link
        if (
            link.owner_identity_digest != owner_digest
            or link.asset_id != asset_id
            or link.revision_id != revision_id
            or link.receipt_sha256 != str(row[10])
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority link identity failed"
            )
        production = receipt.production.manifest
        run = receipt.audible_run.manifest
        if (
            link.audio_sha256 != production.output_sha256
            or link.duration_seconds != production.duration_seconds
            or link.chapter_ids != tuple(ch.chapter_id for ch in run.chapters)
            or link.retention_marker_count != len(run.retention_markers)
            or link.learned_claim_count != len(run.learned_claims)
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority link receipt values failed"
            )
        fresh_row = self._load(run_id)
        if (
            fresh_row is None
            or len(fresh_row) != 14
            or list(fresh_row[:13]) != list(row[:13])
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority row changed during verification"
            )
        self._verify_row_mac(fresh_row)
        try:
            fresh_record = self._store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalAudibleCoordinatorError(
                "audible authority asset disappeared during verification: evidence_conflict"
            ) from exc
        if fresh_record.audio_production_link != link:
            raise LocalAudibleCoordinatorError(
                "audible authority audio production link changed during verification"
            )
        fresh_receipt_payload = _read_private(receipt_path, _MAX_RECEIPT_BYTES)
        fresh_production_payload = _read_private(production_path, 4 * 1024 * 1024)
        fresh_receipt = AudibleExperienceReceipt.reopen_from_file(
            receipt_path,
            signing_key=self._receipt_key,
            production_integrity_key=self._production_key,
        )
        if (
            fresh_receipt_payload != receipt_payload
            or fresh_production_payload != production_payload
            or fresh_receipt != receipt
        ):
            raise LocalAudibleCoordinatorError(
                "audible authority files changed during verification"
            )
        return AudibleAuthority(
            run_id=run_id,
            owner_digest=owner_digest,
            asset_id=asset_id,
            revision_id=revision_id,
            input_digest=str(row[4]),
            config_digest=self._config_digest,
            artifact_digest=str(row[8]),
            receipt_digest=str(row[10]),
            updated_at=str(row[12]),
            receipt=receipt,
            audio_production_link=link,
        )

    def _receipt_and_register(
        self,
        row: DatabaseRow,
        request: LocalAudibleRunRequest,
        inputs: LocalAudibleInputs,
        owner_digest: str,
        production: LocalAudibleProductionArtifact,
        now: datetime,
    ) -> LocalAudibleRunResult:
        if str(row[6]) == "audio_succeeded":
            row = self._advance(
                str(row[0]), expected="audio_succeeded", status="receipting", now=now
            )
        if str(row[6]) != "receipting":
            raise LocalAudibleCoordinatorError("local audible receipt phase conflicts")
        try:
            receipt = issue_audible_experience_receipt(
                owner_digest=owner_digest,
                production=production,
                audible_run=inputs.audible_run,
                signing_key=self._receipt_key,
                production_integrity_key=self._production_key,
                now=now,
            )
        except Exception as exc:
            raise LocalAudibleOutcomeUnknown(
                "local audible receipt outcome requires explicit recovery"
            ) from exc
        row = self._advance(
            str(row[0]),
            expected="receipting",
            status="succeeded",
            receipt_sha256=_sha(receipt.to_json().encode("ascii")),
            now=now,
        )
        return self._register(row, request, inputs, owner_digest, receipt, now)

    def _register(
        self,
        row: DatabaseRow,
        request: LocalAudibleRunRequest,
        inputs: LocalAudibleInputs,
        owner_digest: str,
        receipt: AudibleExperienceReceipt,
        now: datetime,
    ) -> LocalAudibleRunResult:
        if str(row[6]) == "succeeded":
            row = self._advance(
                str(row[0]), expected="succeeded", status="registering", now=now
            )
        if str(row[6]) != "registering":
            raise LocalAudibleCoordinatorError("local audible registration phase conflicts")
        playback = VerifiedAudioPlaybackRuntime(
            receipt_path_resolver=self.receipt_path,
            receipt_key=self._receipt_key,
            production_integrity_key=self._production_key,
        )
        try:
            register_multimedia_audio_production(
                request.asset_id,
                MultimediaAudioRegistrationRequest(
                    expected_revision_id=request.expected_revision_id
                ),
                owner_id=request.owner_id,
                store=self._store,
                playback=playback,
            )
        except Exception as exc:
            raise LocalAudibleOutcomeUnknown(
                "local audible registration outcome requires explicit recovery"
            ) from exc
        row = self._advance(
            str(row[0]), expected="registering", status="registered", now=now
        )
        return LocalAudibleRunResult(
            run_id=str(row[0]), input_digest=inputs.input_digest, receipt=receipt
        )

    def _result(
        self,
        row: DatabaseRow,
        request: LocalAudibleRunRequest,
        inputs: LocalAudibleInputs,
        owner_digest: str,
    ) -> LocalAudibleRunResult:
        self._verify_row(row, request, inputs, owner_digest)
        receipt = self._reopen_receipt(Path(str(row[9])), request, inputs)
        record = self._store.get(request.asset_id, owner_id=request.owner_id)
        if (
            record.asset.revision_id != request.expected_revision_id
            or record.audio_production_link is None
            or record.audio_production_link.receipt_sha256 != str(row[10])
        ):
            raise LocalAudibleCoordinatorError("local audible registration authority drifted")
        return LocalAudibleRunResult(
            run_id=str(row[0]), input_digest=inputs.input_digest, receipt=receipt
        )

    def _inputs(
        self, request: LocalAudibleRunRequest
    ) -> tuple[LocalAudibleInputs, str]:
        self._verify_executables()
        if not isinstance(request, LocalAudibleRunRequest) or not request.owner_id:
            raise ValueError("local audible run request is invalid")
        try:
            record = self._store.get(request.asset_id, owner_id=request.owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalAudibleCoordinatorError("multimedia audio asset is unavailable") from exc
        asset = record.asset
        if (
            asset.revision_id != request.expected_revision_id
            or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest"
            or record.mode != "audio"
            or str(asset.kind) != "audio_experience"
        ):
            raise LocalAudibleCoordinatorError(
                "local audible run requires the current ready cheapest audio revision"
            )
        try:
            inputs = compile_local_audible_inputs(
                record.plan, request.span_requests, resolver=self._resolver
            )
        except Exception as exc:
            raise LocalAudibleCoordinatorError("local audible inputs are unavailable") from exc
        if (
            inputs.asset_id != request.asset_id
            or inputs.revision_id != request.expected_revision_id
        ):
            raise LocalAudibleCoordinatorError("local audible input identity conflicts")
        return inputs, str(asset.owner_user_id)

    def _verify_executables(self) -> None:
        try:
            ffmpeg_digest = _hash_file(Path(self._ffmpeg), 256 * 1024 * 1024)
            ffprobe_digest = _hash_file(Path(self._ffprobe), 256 * 1024 * 1024)
        except (OSError, ValueError) as exc:
            raise LocalAudibleCoordinatorError(
                "local audible executable identity is unavailable"
            ) from exc
        if not hmac.compare_digest(
            ffmpeg_digest, self._ffmpeg_digest
        ) or not hmac.compare_digest(ffprobe_digest, self._ffprobe_digest):
            raise LocalAudibleCoordinatorError("local audible executable identity changed")

    def _produce_track(self, inputs: LocalAudibleInputs) -> LocalAudibleProductionArtifact:
        return produce_local_audible_track(
            inputs,
            output_dir=str(self._root),
            integrity_key=self._production_key,
            ffmpeg_path=self._ffmpeg,
            ffprobe_path=self._ffprobe,
            sample_rate_hz=inputs.sample_rate_hz,
            channels=inputs.channels,
            timeout_seconds=self._timeout,
            publication_id=self._config_digest[:16],
        )

    def _reopen_production(
        self, path: Path, inputs: LocalAudibleInputs
    ) -> LocalAudibleProductionArtifact:
        production = LocalAudibleProductionArtifact.reopen(
            _read_private(path, 4 * 1024 * 1024), self._production_key
        )
        if (
            production.manifest.input_digest != inputs.input_digest
            or production.manifest.audible_run_sha256
            != inputs.audible_run.manifest_sha256
        ):
            raise LocalAudibleCoordinatorError("local audible production authority drifted")
        return production

    def _reopen_receipt(
        self, path: Path, request: LocalAudibleRunRequest, inputs: LocalAudibleInputs
    ) -> AudibleExperienceReceipt:
        receipt = AudibleExperienceReceipt.reopen_from_file(
            path,
            signing_key=self._receipt_key,
            production_integrity_key=self._production_key,
        )
        if (
            receipt.asset_id != request.asset_id
            or receipt.revision_id != request.expected_revision_id
            or receipt.audible_run != inputs.audible_run
        ):
            raise LocalAudibleCoordinatorError("local audible receipt authority drifted")
        return receipt

    def _production_manifest_path(self, inputs: LocalAudibleInputs) -> Path:
        directory = self._root / (
            f"{inputs.asset_id}-{inputs.revision_id}-audible-{inputs.input_digest[:16]}"
            f"-{self._config_digest[:16]}"
        )
        return directory / "audible.json"

    def _insert(self, values: list[object]) -> bool:
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_audible.begin") as connection:
            connection.execute(_DDL)
            existing = connection.execute(
                "SELECT * FROM multimedia_local_audible_runs WHERE run_id=?", [values[0]]
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                "INSERT INTO multimedia_local_audible_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [*values, _mac(values, self._key)],
            )
            return True

    def _advance(
        self,
        run_id: str,
        *,
        expected: AudibleRunStatus,
        status: AudibleRunStatus,
        now: datetime,
        production_sha256: str | None = None,
        receipt_sha256: str | None = None,
    ) -> DatabaseRow:
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.local_audible.advance") as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_local_audible_runs WHERE run_id=?", [run_id]
            ).fetchone()
            if (
                row is None
                or str(row[6]) != expected
                or not isinstance(row[13], str)
                or not hmac.compare_digest(row[13], _mac(list(row[:13]), self._key))
            ):
                raise LocalAudibleCoordinatorError("stored local audible phase conflicts")
            values = list(row[:13])
            values[6] = status
            if production_sha256 is not None:
                values[8] = production_sha256
            if receipt_sha256 is not None:
                values[10] = receipt_sha256
            values[12] = _timestamp(now)
            mac = _mac(values, self._key)
            connection.execute(
                "UPDATE multimedia_local_audible_runs SET status=?, production_sha256=?, "
                "receipt_sha256=?, updated_at=?, row_mac=? WHERE run_id=?",
                [values[6], values[8], values[10], values[12], mac, run_id],
            )
            return tuple([*values, mac])

    def _load(self, run_id: str) -> DatabaseRow | None:
        if not Path(self._db_path).exists():
            return None
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_audible_runs WHERE run_id=?", [run_id]
                ).fetchone()
        except duckdb.CatalogException:
            return None
        except Exception as exc:
            raise LocalAudibleCoordinatorError("local audible database is unavailable") from exc

    def _rows_for_identity(
        self, asset_id: str, revision_id: str
    ) -> list[DatabaseRow]:
        if not Path(self._db_path).exists():
            return []
        try:
            with connect_read(self._db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_audible_runs "
                    "WHERE asset_id=? AND revision_id=?",
                    [asset_id, revision_id],
                ).fetchall()
        except Exception as exc:
            raise LocalAudibleCoordinatorError("local audible database is unavailable") from exc

    def _find_registered_row(
        self, owner_digest: str, asset_id: str, revision_id: str
    ) -> DatabaseRow:
        if not Path(self._db_path).exists():
            raise LocalAudibleCoordinatorError(
                "audible authority database is unavailable: evidence_unavailable"
            )
        try:
            with connect_read(self._db_path) as connection:
                try:
                    rows = connection.execute(
                        "SELECT * FROM multimedia_local_audible_runs "
                        "WHERE owner_digest=? AND asset_id=? AND revision_id=? "
                        "AND status='registered'",
                        [owner_digest, asset_id, revision_id],
                    ).fetchall()
                except duckdb.CatalogException:
                    raise LocalAudibleCoordinatorError(
                        "audible authority table is missing: evidence_unavailable"
                    ) from None
        except LocalAudibleCoordinatorError:
            raise
        except Exception as exc:
            raise LocalAudibleCoordinatorError(
                "audible authority database is unavailable: evidence_unavailable"
            ) from exc
        if len(rows) == 0:
            raise LocalAudibleCoordinatorError(
                "audible authority registered row is missing: evidence_unavailable"
            )
        if len(rows) > 1:
            raise LocalAudibleCoordinatorError(
                "audible authority has multiple registered rows: evidence_unavailable"
            )
        return rows[0]

    def _verify_row(
        self,
        row: DatabaseRow,
        request: LocalAudibleRunRequest,
        inputs: LocalAudibleInputs,
        owner_digest: str,
    ) -> None:
        if (
            row is None
            or len(row) != 14
            or list(row[1:6])
            != [
                owner_digest,
                request.asset_id,
                request.expected_revision_id,
                inputs.input_digest,
                self._config_digest,
            ]
            or not isinstance(row[13], str)
            or not hmac.compare_digest(row[13], _mac(list(row[:13]), self._key))
        ):
            raise LocalAudibleCoordinatorError("stored local audible integrity failed")

    def _verify_row_mac(self, row: DatabaseRow) -> None:
        if (
            not isinstance(row[13], str)
            or not hmac.compare_digest(row[13], _mac(list(row[:13]), self._key))
        ):
            raise LocalAudibleCoordinatorError("stored local audible integrity failed")


def _run_id(owner_digest: str, input_digest: str, config_digest: str) -> str:
    return "mmlocalaudible_" + hashlib.sha256(
        f"{owner_digest}\0{input_digest}\0{config_digest}".encode("ascii")
    ).hexdigest()


def _private_db_path(value: str) -> str:
    path = Path(value)
    parent = path.parent.lstat()
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.parent.is_symlink()
        or path.parent.resolve() != path.parent
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise ValueError("local audible database parent must be private")
    return str(path)


def _private_directory(value: str) -> Path:
    path = Path(value)
    info = path.lstat()
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.resolve() != path
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("local audible output directory must be private")
    return path


def _trusted_executable(value: str) -> tuple[str, str]:
    path = Path(value).resolve(strict=True)
    info = path.stat()
    if not path.is_file() or not os.access(path, os.X_OK) or info.st_size > 256 * 1024 * 1024:
        raise ValueError("local audible executable is not trusted")
    return str(path), _hash_file(path, 256 * 1024 * 1024)


def _hash_file(path: Path, maximum: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > maximum:
                raise ValueError("local audible executable exceeds its byte ceiling")
            digest.update(chunk)
    return digest.hexdigest()


def _read_private(path: Path, maximum: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
    except OSError:
        raise LocalAudibleCoordinatorError("local audible artifact is unavailable") from None
    try:
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 1 <= info.st_size <= maximum
        ):
            raise LocalAudibleCoordinatorError("local audible artifact is not private")
        payload = b""
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise LocalAudibleCoordinatorError("local audible artifact was truncated")
            payload += chunk
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise LocalAudibleCoordinatorError("local audible artifact changed while reading")
        return payload
    finally:
        os.close(descriptor)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local audible timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "AudibleAuthority",
    "LocalAudibleCoordinator",
    "LocalAudibleCoordinatorError",
    "LocalAudibleOutcomeUnknown",
    "LocalAudibleRunRequest",
    "LocalAudibleRunResult",
]
