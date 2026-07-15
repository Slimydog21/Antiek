"""Owner-bound preparation and recovery for the cheapest local audio workstation."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .graph_evidence import (
    MultimediaGraphEvidenceUnavailable,
    load_canonical_multimedia_chunks,
)
from .local_audible_coordinator import (
    LocalAudibleOutcomeUnknown,
    LocalAudibleRunRequest,
    LocalAudibleRunResult,
)
from .local_audible_tts import (
    PreparedAudibleSpanTTSRequest,
    prepare_local_audible_span_requests,
)
from .local_tts import LocalTTSArtifact, LocalTTSError, LocalTTSOutcomeUnknown
from .read_model import MultimediaAssetRecord, MultimediaAssetStore

DatabaseRow = tuple[object, ...]

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_audible_sets (
 set_id TEXT PRIMARY KEY, owner_digest TEXT NOT NULL, asset_id TEXT NOT NULL,
 revision_id TEXT NOT NULL, plan_digest TEXT NOT NULL, status TEXT NOT NULL,
 request_ids_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 row_mac TEXT NOT NULL)
"""

AudiblePreparedStatus = Literal[
    "preparing",
    "preparation_unknown",
    "ready_to_produce",
    "production_unknown",
    "registered",
]


class LocalAudibleWorkstationError(RuntimeError):
    """Audible prepared-set ownership or durable evidence failed closed."""


class LocalAudibleWorkstationTTS(Protocol):
    def synthesize(
        self, request: PreparedAudibleSpanTTSRequest, *, now: datetime
    ) -> LocalTTSArtifact: ...

    def recover(self, request: PreparedAudibleSpanTTSRequest) -> LocalTTSArtifact: ...

    def reopen(self, request: PreparedAudibleSpanTTSRequest) -> LocalTTSArtifact: ...


class LocalAudibleWorkstationProduction(Protocol):
    def produce(
        self, request: LocalAudibleRunRequest, *, now: datetime
    ) -> LocalAudibleRunResult: ...

    def recover(
        self, request: LocalAudibleRunRequest, *, now: datetime
    ) -> LocalAudibleRunResult: ...


class _ReadModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocalAudiblePreparedChapter(_ReadModel):
    chapter_id: str
    title: str
    span_count: int = Field(ge=1)
    ready_span_count: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    source_count: int = Field(ge=0)
    remember_ready: bool
    recap_ready: bool
    learned_claim_count: int = Field(ge=0)


class LocalAudiblePreparedSet(_ReadModel):
    set_id: str
    asset_id: str
    revision_id: str
    status: AudiblePreparedStatus
    recoverable: bool
    cost_usd: Literal[0] = 0
    playback_ready: bool
    total_duration_seconds: float = Field(ge=0)
    chapters: tuple[LocalAudiblePreparedChapter, ...] = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class LocalAudibleWorkstationRuntime:
    db_path: str
    signing_key: bytes
    store: MultimediaAssetStore
    tts: LocalAudibleWorkstationTTS
    production: LocalAudibleWorkstationProduction
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if (
            not Path(self.db_path).is_absolute()
            or not isinstance(self.signing_key, bytes)
            or len(self.signing_key) < 32
        ):
            raise ValueError("local audible workstation configuration is invalid")

    def prepare(
        self, asset_id: str, expected_revision_id: str, *, owner_id: str
    ) -> LocalAudiblePreparedSet:
        record, requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        set_id = _set_id(owner_digest, asset_id, expected_revision_id, plan_digest)
        row = self._load(set_id)
        now = _clock(self.clock)
        if row is not None:
            self._verify_row(row, owner_digest, asset_id, expected_revision_id, plan_digest)
            return self._inspect(row, record, requests)
        values: list[object] = [
            set_id,
            owner_digest,
            asset_id,
            expected_revision_id,
            plan_digest,
            "preparing",
            "[]",
            _timestamp(now),
            _timestamp(now),
        ]
        if not self._insert(values):
            row = self._required(
                set_id, owner_digest, asset_id, expected_revision_id, plan_digest
            )
            return self._inspect(row, record, requests)
        try:
            artifacts = tuple(self.tts.synthesize(request, now=now) for request in requests)
        except LocalTTSOutcomeUnknown:
            row = self._update(set_id, status="preparation_unknown", now=now)
            return self._inspect(row, record, requests)
        row = self._update(
            set_id,
            status="ready_to_produce",
            request_ids=tuple(artifact.request_id for artifact in artifacts),
            now=now,
        )
        return self._inspect(row, record, requests)

    def recover(
        self,
        asset_id: str,
        expected_revision_id: str,
        set_id: str,
        *,
        owner_id: str,
    ) -> LocalAudiblePreparedSet:
        record, requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(
            set_id, owner_digest, asset_id, expected_revision_id, plan_digest
        )
        now = _clock(self.clock)
        if str(row[5]) in {"preparing", "preparation_unknown"}:
            artifacts: list[LocalTTSArtifact] = []
            for request in requests:
                try:
                    artifacts.append(self.tts.synthesize(request, now=now))
                except LocalTTSOutcomeUnknown:
                    try:
                        artifacts.append(self.tts.recover(request))
                    except LocalTTSError:
                        row = self._update(
                            set_id, status="preparation_unknown", now=now
                        )
                        return self._inspect(row, record, requests)
            row = self._update(
                set_id,
                status="ready_to_produce",
                request_ids=tuple(artifact.request_id for artifact in artifacts),
                now=now,
            )
            return self._inspect(row, record, requests)
        if str(row[5]) != "production_unknown":
            raise LocalAudibleWorkstationError(
                "local audible prepared set is not recoverable"
            )
        run_request = self._run_request(row, requests, owner_id)
        try:
            self.production.produce(run_request, now=now)
        except LocalAudibleOutcomeUnknown:
            try:
                self.production.recover(run_request, now=now)
            except LocalAudibleOutcomeUnknown:
                return self._inspect(row, record, requests)
        row = self._update(set_id, status="registered", now=now)
        return self._inspect(row, record, requests)

    def produce(
        self,
        asset_id: str,
        expected_revision_id: str,
        set_id: str,
        *,
        owner_id: str,
    ) -> LocalAudiblePreparedSet:
        record, requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(
            set_id, owner_digest, asset_id, expected_revision_id, plan_digest
        )
        inspected = self._inspect(row, record, requests)
        if inspected.status != "ready_to_produce" or any(
            chapter.ready_span_count != chapter.span_count for chapter in inspected.chapters
        ):
            raise LocalAudibleWorkstationError(
                "local audible prepared set is incomplete"
            )
        now = _clock(self.clock)
        row = self._update(set_id, status="production_unknown", now=now)
        try:
            self.production.produce(self._run_request(row, requests, owner_id), now=now)
        except LocalAudibleOutcomeUnknown:
            return self._inspect(row, record, requests)
        row = self._update(set_id, status="registered", now=now)
        return self._inspect(row, record, requests)

    def inspect(
        self,
        asset_id: str,
        expected_revision_id: str,
        set_id: str,
        *,
        owner_id: str,
    ) -> LocalAudiblePreparedSet:
        record, requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(
            set_id, owner_digest, asset_id, expected_revision_id, plan_digest
        )
        return self._inspect(row, record, requests)

    def _authority(
        self, asset_id: str, revision_id: str, owner_id: str
    ) -> tuple[
        MultimediaAssetRecord,
        tuple[PreparedAudibleSpanTTSRequest, ...],
        str,
        str,
    ]:
        try:
            record = self.store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalAudibleWorkstationError("multimedia audio asset is unavailable") from exc
        asset = record.asset
        if (
            asset.revision_id != revision_id
            or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest"
            or record.mode != "audio"
            or str(asset.kind) != "audio_experience"
        ):
            raise LocalAudibleWorkstationError(
                "local audible workstation requires the current ready cheapest audio revision"
            )
        try:
            canonical_ids = tuple(
                dict.fromkeys(
                    span.chunk_id
                    for line in record.plan.script_lines
                    if line.evidence_derivation is not None
                    for span in line.evidence_derivation.spans
                    if span.authority_kind == "canonical_graph"
                )
            )
            canonical_chunks = (
                load_canonical_multimedia_chunks(
                    self.db_path, canonical_ids, owner_id=owner_id
                )
                if canonical_ids
                else None
            )
            requests = prepare_local_audible_span_requests(
                record.plan,
                asset_id=asset_id,
                revision_id=revision_id,
                canonical_chunks=canonical_chunks,
            )
        except (MultimediaGraphEvidenceUnavailable, OSError, RuntimeError, ValueError) as exc:
            raise LocalAudibleWorkstationError(
                "local audible workstation requires grounded spoken content"
            ) from exc
        plan_digest = hashlib.sha256(
            _canonical(record.plan.model_dump(mode="json"))
        ).hexdigest()
        return record, requests, str(asset.owner_user_id), plan_digest

    def _inspect(
        self,
        row: DatabaseRow,
        record: MultimediaAssetRecord,
        requests: tuple[PreparedAudibleSpanTTSRequest, ...],
    ) -> LocalAudiblePreparedSet:
        request_ids = _ids(str(row[6]))
        ready: dict[str, tuple[LocalTTSArtifact, PreparedAudibleSpanTTSRequest]] = {}
        for index, request in enumerate(requests):
            try:
                artifact = self.tts.reopen(request)
                if index < len(request_ids) and artifact.request_id == request_ids[index]:
                    ready[request.paragraph_id] = (artifact, request)
            except (LocalTTSError, ValueError):
                pass
        chapters: list[LocalAudiblePreparedChapter] = []
        for chapter in record.plan.chapters:
            chapter_requests = tuple(
                request for request in requests if request.chapter_id == chapter.chapter_id
            )
            if not chapter_requests:
                continue
            ready_rows = tuple(
                ready[request.paragraph_id]
                for request in chapter_requests
                if request.paragraph_id in ready
            )
            sources = {
                source_id
                for request in chapter_requests
                for source_id in request.source_chunk_ids
            }
            chapters.append(
                LocalAudiblePreparedChapter(
                    chapter_id=chapter.chapter_id,
                    title=chapter.title,
                    span_count=len(chapter_requests),
                    ready_span_count=len(ready_rows),
                    duration_seconds=round(
                        sum(artifact.duration_seconds for artifact, _request in ready_rows), 3
                    ),
                    source_count=len(sources),
                    remember_ready=any(
                        request.marker_kind == "remember"
                        and request.paragraph_id in ready
                        for request in chapter_requests
                    ),
                    recap_ready=any(
                        request.marker_kind == "recap" and request.paragraph_id in ready
                        for request in chapter_requests
                    ),
                    learned_claim_count=sum(
                        request.marker_kind == "content" and bool(request.source_chunk_ids)
                        for request in chapter_requests
                    ),
                )
            )
        status = str(row[5])
        if status == "ready_to_produce" and any(
            chapter.ready_span_count != chapter.span_count for chapter in chapters
        ):
            status = "preparation_unknown"
        return LocalAudiblePreparedSet(
            set_id=str(row[0]),
            asset_id=str(row[2]),
            revision_id=str(row[3]),
            status=status,  # type: ignore[arg-type]
            recoverable=status
            in {"preparing", "preparation_unknown", "production_unknown"},
            playback_ready=status == "registered",
            total_duration_seconds=round(
                sum(chapter.duration_seconds for chapter in chapters), 3
            ),
            chapters=tuple(chapters),
        )

    def _run_request(
        self,
        row: DatabaseRow,
        requests: tuple[PreparedAudibleSpanTTSRequest, ...],
        owner_id: str,
    ) -> LocalAudibleRunRequest:
        return LocalAudibleRunRequest(
            owner_id=owner_id,
            asset_id=str(row[2]),
            expected_revision_id=str(row[3]),
            span_requests=tuple(requests),
        )

    def _required(
        self,
        set_id: str,
        owner_digest: str,
        asset_id: str,
        revision_id: str,
        plan_digest: str,
    ) -> DatabaseRow:
        if set_id != _set_id(owner_digest, asset_id, revision_id, plan_digest):
            raise LocalAudibleWorkstationError("local audible prepared set is unavailable")
        row = self._load(set_id)
        if row is None:
            raise LocalAudibleWorkstationError("local audible prepared set is unavailable")
        self._verify_row(row, owner_digest, asset_id, revision_id, plan_digest)
        return row

    def _load(self, set_id: str) -> DatabaseRow | None:
        if not Path(self.db_path).exists():
            return None
        try:
            with connect_read(self.db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_audible_sets WHERE set_id=?", [set_id]
                ).fetchone()
        except duckdb.CatalogException:
            return None
        except Exception as exc:
            raise LocalAudibleWorkstationError(
                "local audible workstation database is unavailable"
            ) from exc

    def _insert(self, values: list[object]) -> bool:
        coordinator = FlockWriteCoordinator(self.db_path)
        with coordinator.acquire_write_context(
            "multimedia.local_audible_workstation.prepare"
        ) as connection:
            connection.execute(_DDL)
            current = connection.execute(
                "SELECT * FROM multimedia_local_audible_sets WHERE set_id=?", [values[0]]
            ).fetchone()
            if current is not None:
                return False
            connection.execute(
                "INSERT INTO multimedia_local_audible_sets VALUES (?,?,?,?,?,?,?,?,?,?)",
                [*values, _mac(values, self.signing_key)],
            )
            return True

    def _update(
        self,
        set_id: str,
        *,
        status: AudiblePreparedStatus,
        now: datetime,
        request_ids: tuple[str, ...] | None = None,
    ) -> DatabaseRow:
        coordinator = FlockWriteCoordinator(self.db_path)
        with coordinator.acquire_write_context(
            "multimedia.local_audible_workstation.update"
        ) as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_local_audible_sets WHERE set_id=?", [set_id]
            ).fetchone()
            if (
                row is None
                or not isinstance(row[9], str)
                or not hmac.compare_digest(
                    row[9], _mac(list(row[:9]), self.signing_key)
                )
            ):
                raise LocalAudibleWorkstationError(
                    "stored local audible prepared-set integrity failed"
                )
            values = list(row[:9])
            values[5] = status
            if request_ids is not None:
                values[6] = json.dumps(request_ids, separators=(",", ":"))
            values[8] = _timestamp(now)
            mac = _mac(values, self.signing_key)
            connection.execute(
                "UPDATE multimedia_local_audible_sets SET status=?, request_ids_json=?, "
                "updated_at=?, row_mac=? WHERE set_id=?",
                [values[5], values[6], values[8], mac, set_id],
            )
            return tuple([*values, mac])

    def _verify_row(
        self,
        row: DatabaseRow,
        owner_digest: str,
        asset_id: str,
        revision_id: str,
        plan_digest: str,
    ) -> None:
        if (
            row is None
            or len(row) != 10
            or list(row[1:5])
            != [owner_digest, asset_id, revision_id, plan_digest]
            or not isinstance(row[9], str)
            or not hmac.compare_digest(row[9], _mac(list(row[:9]), self.signing_key))
        ):
            raise LocalAudibleWorkstationError(
                "stored local audible prepared-set integrity failed"
            )


def _set_id(owner_digest: str, asset_id: str, revision_id: str, plan_digest: str) -> str:
    return "mmlocalaudibleset_" + hashlib.sha256(
        f"{owner_digest}\0{asset_id}\0{revision_id}\0{plan_digest}".encode("ascii")
    ).hexdigest()


def _ids(value: str) -> tuple[str, ...]:
    try:
        rows = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        raise LocalAudibleWorkstationError(
            "stored local audible request identifiers are invalid"
        ) from None
    if (
        not isinstance(rows, list)
        or len(rows) > 4096
        or any(not isinstance(row, str) for row in rows)
    ):
        raise LocalAudibleWorkstationError(
            "stored local audible request identifiers are invalid"
        )
    return tuple(rows)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local audible workstation timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clock(factory: Callable[[], datetime]) -> datetime:
    value = factory()
    if not isinstance(value, datetime):
        raise ValueError("local audible workstation clock is invalid")
    return value


__all__ = [
    "LocalAudiblePreparedChapter",
    "LocalAudiblePreparedSet",
    "LocalAudibleWorkstationError",
    "LocalAudibleWorkstationRuntime",
]
