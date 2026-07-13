"""Owner-bound prepared sets for the zero-provider multimedia workstation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .chapter_tts_production import (
    PreparedChapterTTSRequest,
    prepare_chapter_tts_request,
)
from .local_production_coordinator import (
    LocalNarrationRunRequest,
    LocalProductionOutcomeUnknown,
    LocalVideoRunArtifact,
    LocalVideoRunRequest,
)
from .local_source_card import (
    LocalSourceCardArtifact,
    LocalSourceCardRequest,
)
from .local_tts import LocalTTSArtifact, LocalTTSError, LocalTTSOutcomeUnknown
from .local_video_bridge import LocalSourceCardInput
from .read_model import MultimediaAssetRecord, MultimediaAssetStore
from .visual_selection import EvidenceVerifier

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_local_prepared_sets (
 set_id TEXT PRIMARY KEY, owner_digest TEXT NOT NULL, asset_id TEXT NOT NULL,
 revision_id TEXT NOT NULL, plan_digest TEXT NOT NULL, status TEXT NOT NULL,
 request_ids_json TEXT NOT NULL, card_ids_json TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, row_mac TEXT NOT NULL)
"""

PreparedStatus = Literal[
    "preparing", "preparation_unknown", "review_required",
    "ready_to_produce", "production_unknown", "registered",
]
DatabaseRow = tuple[object, ...]


class LocalWorkstationError(RuntimeError):
    """The local workstation set failed an ownership or authority check."""


class LocalWorkstationTTS(Protocol):
    def synthesize(
        self, request: PreparedChapterTTSRequest, *, now: datetime
    ) -> LocalTTSArtifact: ...

    def recover(self, request: PreparedChapterTTSRequest) -> LocalTTSArtifact: ...

    def reopen(self, request: PreparedChapterTTSRequest) -> LocalTTSArtifact: ...


class LocalWorkstationCards(Protocol):
    def create(
        self, request: LocalSourceCardRequest, *, owner_id: str, now: datetime
    ) -> LocalSourceCardArtifact: ...

    def reopen(
        self, card_id: str, request: LocalSourceCardRequest, *, owner_id: str
    ) -> LocalSourceCardArtifact: ...

    def attest(
        self, card_id: str, request: LocalSourceCardRequest, *, owner_id: str,
        reviewer_id: str, operator_signing_key: bytes, attested_at: datetime,
    ) -> object: ...


class LocalWorkstationVideo(Protocol):
    def register(
        self, request: LocalVideoRunRequest, *, now: datetime
    ) -> LocalVideoRunArtifact: ...

    def recover(
        self, request: LocalVideoRunRequest, *, now: datetime
    ) -> LocalVideoRunArtifact: ...


class _ReadModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocalPreparedChapter(_ReadModel):
    chapter_id: str
    title: str
    narration_ready: bool
    card_id: str | None = None
    card_ready: bool
    attested: bool
    source_count: int = Field(ge=0)


class LocalPreparedSet(_ReadModel):
    set_id: str
    asset_id: str
    revision_id: str
    status: PreparedStatus
    recoverable: bool
    cost_usd: float = 0.0
    playback_ready: bool
    chapters: tuple[LocalPreparedChapter, ...]


@dataclass(frozen=True)
class LocalWorkstationRuntime:
    db_path: str
    signing_key: bytes
    operator_signing_key: bytes
    store: MultimediaAssetStore
    tts: LocalWorkstationTTS
    cards: LocalWorkstationCards
    video: LocalWorkstationVideo
    verify_evidence: EvidenceVerifier
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if (
            not Path(self.db_path).is_absolute()
            or not isinstance(self.signing_key, bytes) or len(self.signing_key) < 32
            or not isinstance(self.operator_signing_key, bytes)
            or len(self.operator_signing_key) != 32
        ):
            raise ValueError("local workstation persistence configuration is invalid")

    def prepare(
        self, asset_id: str, expected_revision_id: str, *, owner_id: str
    ) -> LocalPreparedSet:
        record, requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        set_id = _set_id(owner_digest, asset_id, expected_revision_id, plan_digest)
        row = self._load(set_id)
        now = _clock(self.clock)
        if row is None:
            values: list[object] = [
                set_id, owner_digest, asset_id, expected_revision_id, plan_digest,
                "preparing", "[]", "[]", _timestamp(now), _timestamp(now),
            ]
            elected = self._insert(values)
            if not elected:
                row = self._required(
                    set_id, owner_digest, asset_id, expected_revision_id, plan_digest
                )
                return self._inspect(row, record, requests, card_requests, owner_id)
        else:
            self._verify_row(row, owner_digest, asset_id, expected_revision_id, plan_digest)
            return self._inspect(row, record, requests, card_requests, owner_id)
        try:
            artifacts = tuple(self.tts.synthesize(request, now=now) for request in requests)
        except LocalTTSOutcomeUnknown:
            row = self._update(set_id, status="preparation_unknown", now=now)
            return self._inspect(row, record, requests, card_requests, owner_id)
        cards = tuple(
            self.cards.create(request, owner_id=owner_id, now=now)
            for request in card_requests
        )
        row = self._update(
            set_id,
            status="review_required",
            request_ids=tuple(row.request_id for row in artifacts),
            card_ids=tuple(row.card_id for row in cards),
            now=now,
        )
        return self._inspect(row, record, requests, card_requests, owner_id)

    def recover(
        self, asset_id: str, expected_revision_id: str, set_id: str, *, owner_id: str
    ) -> LocalPreparedSet:
        record, requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(set_id, owner_digest, asset_id, expected_revision_id, plan_digest)
        now = _clock(self.clock)
        if row[5] in {"preparing", "preparation_unknown"}:
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
                        return self._inspect(
                            row, record, requests, card_requests, owner_id
                        )
            cards = tuple(
                self.cards.create(request, owner_id=owner_id, now=now)
                for request in card_requests
            )
            row = self._update(
                set_id, status="review_required",
                request_ids=tuple(item.request_id for item in artifacts),
                card_ids=tuple(item.card_id for item in cards), now=now,
            )
            return self._inspect(row, record, requests, card_requests, owner_id)
        if row[5] != "production_unknown":
            raise LocalWorkstationError("local prepared set is not recoverable")
        video_request = self._video_request(row, requests, card_requests, owner_id)
        try:
            self.video.recover(video_request, now=now)
            self.video.register(video_request, now=now)
        except LocalProductionOutcomeUnknown:
            return self._inspect(row, record, requests, card_requests, owner_id)
        row = self._update(set_id, status="registered", now=now)
        return self._inspect(row, record, requests, card_requests, owner_id)

    def attest(
        self, asset_id: str, expected_revision_id: str, set_id: str, card_id: str,
        *, owner_id: str,
    ) -> LocalPreparedSet:
        record, requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(set_id, owner_digest, asset_id, expected_revision_id, plan_digest)
        card_ids = _ids(str(row[7]))
        try:
            index = card_ids.index(card_id)
        except ValueError:
            raise LocalWorkstationError("local source card is unavailable") from None
        now = _clock(self.clock)
        self.cards.attest(
            card_id, card_requests[index], owner_id=owner_id, reviewer_id=owner_id,
            operator_signing_key=self.operator_signing_key, attested_at=now,
        )
        inspected = self._inspect(row, record, requests, card_requests, owner_id)
        status: PreparedStatus = (
            "ready_to_produce" if all(item.attested for item in inspected.chapters)
            else "review_required"
        )
        row = self._update(set_id, status=status, now=now)
        return self._inspect(row, record, requests, card_requests, owner_id)

    def produce(
        self, asset_id: str, expected_revision_id: str, set_id: str, *, owner_id: str
    ) -> LocalPreparedSet:
        record, requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(set_id, owner_digest, asset_id, expected_revision_id, plan_digest)
        inspected = self._inspect(row, record, requests, card_requests, owner_id)
        if inspected.status != "ready_to_produce" or not all(
            item.attested for item in inspected.chapters
        ):
            raise LocalWorkstationError("local prepared set requires explicit review")
        now = _clock(self.clock)
        row = self._update(set_id, status="production_unknown", now=now)
        try:
            self.video.register(
                self._video_request(row, requests, card_requests, owner_id), now=now
            )
        except LocalProductionOutcomeUnknown:
            return self._inspect(row, record, requests, card_requests, owner_id)
        row = self._update(set_id, status="registered", now=now)
        return self._inspect(row, record, requests, card_requests, owner_id)

    def inspect(
        self, asset_id: str, expected_revision_id: str, set_id: str, *, owner_id: str
    ) -> LocalPreparedSet:
        record, requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(set_id, owner_digest, asset_id, expected_revision_id, plan_digest)
        return self._inspect(row, record, requests, card_requests, owner_id)

    def preview_card(
        self, asset_id: str, expected_revision_id: str, set_id: str, card_id: str,
        *, owner_id: str,
    ) -> bytes:
        _record, _requests, card_requests, owner_digest, plan_digest = self._authority(
            asset_id, expected_revision_id, owner_id
        )
        row = self._required(
            set_id, owner_digest, asset_id, expected_revision_id, plan_digest
        )
        card_ids = _ids(str(row[7]))
        try:
            index = card_ids.index(card_id)
        except ValueError:
            raise LocalWorkstationError("local source card is unavailable") from None
        card = self.cards.reopen(card_id, card_requests[index], owner_id=owner_id)
        return _read_private_png(card.output_path, card.output_sha256)

    def _authority(
        self, asset_id: str, revision_id: str, owner_id: str
    ) -> tuple[
        MultimediaAssetRecord,
        tuple[PreparedChapterTTSRequest, ...],
        tuple[LocalSourceCardRequest, ...],
        str,
        str,
    ]:
        try:
            record = self.store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise LocalWorkstationError("multimedia asset is unavailable") from exc
        asset = record.asset
        if (
            asset.revision_id != revision_id or str(asset.status) != "ready"
            or str(asset.route_policy) != "cheapest" or record.mode == "audio"
            or str(asset.kind) == "audio_experience"
        ):
            raise LocalWorkstationError(
                "local workstation requires the current ready cheapest video revision"
            )
        plan = record.plan
        spoken = tuple(
            chapter for chapter in plan.chapters
            if any(line.line_id.split("-line-", 1)[0] == chapter.chapter_id for line in plan.script_lines)
        )
        requests = tuple(
            prepare_chapter_tts_request(
                plan, asset_id=asset_id, revision_id=revision_id,
                provider="local_executable_tts", model="macos-say-v1",
                voice="narrator", chapter_id=chapter.chapter_id,
            )
            for chapter in spoken
        )
        card_requests = tuple(
            LocalSourceCardRequest(
                asset_id=asset_id, revision_id=revision_id, chapter_id=chapter.chapter_id,
                scene_id=f"scene-{chapter.chapter_id}", title=chapter.title,
                information_purpose=chapter.purpose,
                source_chunk_ids=request.source_chunk_ids,
            )
            for chapter, request in zip(spoken, requests, strict=True)
        )
        if not requests or any(not request.source_chunk_ids for request in card_requests):
            raise LocalWorkstationError("local workstation requires grounded spoken chapters")
        plan_digest = hashlib.sha256(
            _canonical(record.plan.model_dump(mode="json"))
        ).hexdigest()
        return record, requests, card_requests, str(asset.owner_user_id), plan_digest

    def _inspect(
        self,
        row: DatabaseRow,
        record: MultimediaAssetRecord,
        requests: tuple[PreparedChapterTTSRequest, ...],
        card_requests: tuple[LocalSourceCardRequest, ...],
        owner_id: str,
    ) -> LocalPreparedSet:
        request_ids, card_ids = _ids(str(row[6])), _ids(str(row[7]))
        chapters: list[LocalPreparedChapter] = []
        for index, (request, card_request) in enumerate(
            zip(requests, card_requests, strict=True)
        ):
            narration_ready = False
            card_ready = False
            attested = False
            card_id = card_ids[index] if index < len(card_ids) else None
            try:
                artifact = self.tts.reopen(request)
                narration_ready = index < len(request_ids) and artifact.request_id == request_ids[index]
            except (LocalTTSError, ValueError):
                pass
            if card_id is not None:
                try:
                    card = self.cards.reopen(card_id, card_request, owner_id=owner_id)
                    card_ready = True
                    self.verify_evidence(card.selection(), card.output_sha256)
                    attested = True
                except (RuntimeError, ValueError):
                    pass
            chapters.append(
                LocalPreparedChapter(
                    chapter_id=request.chapter_id,
                    title=card_request.title,
                    narration_ready=narration_ready,
                    card_id=card_id,
                    card_ready=card_ready,
                    attested=attested,
                    source_count=len(request.source_chunk_ids),
                )
            )
        status = str(row[5])
        if status in {"review_required", "ready_to_produce"}:
            status = (
                "ready_to_produce"
                if chapters and all(chapter.attested for chapter in chapters)
                else "review_required"
            )
        return LocalPreparedSet(
            set_id=str(row[0]), asset_id=str(row[2]), revision_id=str(row[3]),
            status=status,  # type: ignore[arg-type]
            recoverable=status in {"preparing", "preparation_unknown", "production_unknown"},
            playback_ready=status == "registered",
            chapters=tuple(chapters),
        )

    def _video_request(
        self, row: DatabaseRow,
        requests: tuple[PreparedChapterTTSRequest, ...],
        card_requests: tuple[LocalSourceCardRequest, ...], owner_id: str,
    ) -> LocalVideoRunRequest:
        card_ids = _ids(str(row[7]))
        if len(card_ids) != len(card_requests):
            raise LocalWorkstationError("local prepared set is incomplete")
        return LocalVideoRunRequest(
            narration=LocalNarrationRunRequest(
                owner_id=owner_id, asset_id=str(row[2]), expected_revision_id=str(row[3]),
                chapter_requests=tuple(requests),
            ),
            source_cards=tuple(
                LocalSourceCardInput(card_id, request)
                for card_id, request in zip(card_ids, card_requests, strict=True)
            ),
        )

    def _required(
        self, set_id: str, owner_digest: str, asset_id: str,
        revision_id: str, plan_digest: str,
    ) -> DatabaseRow:
        expected = _set_id(owner_digest, asset_id, revision_id, plan_digest)
        if set_id != expected:
            raise LocalWorkstationError("local prepared set is unavailable")
        row = self._load(set_id)
        if row is None:
            raise LocalWorkstationError("local prepared set is unavailable")
        self._verify_row(row, owner_digest, asset_id, revision_id, plan_digest)
        return row

    def _load(self, set_id: str) -> DatabaseRow | None:
        if not Path(self.db_path).exists():
            return None
        try:
            with connect_read(self.db_path) as connection:
                return connection.execute(
                    "SELECT * FROM multimedia_local_prepared_sets WHERE set_id=?", [set_id]
                ).fetchone()
        except duckdb.CatalogException:
            return None
        except Exception as exc:
            raise LocalWorkstationError("local workstation database is unavailable") from exc

    def _insert(self, values: list[object]) -> bool:
        coordinator = FlockWriteCoordinator(self.db_path)
        with coordinator.acquire_write_context("multimedia.local_workstation.prepare") as connection:
            connection.execute(_DDL)
            current = connection.execute(
                "SELECT * FROM multimedia_local_prepared_sets WHERE set_id=?", [values[0]]
            ).fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO multimedia_local_prepared_sets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [*values, _mac(values, self.signing_key)],
                )
                return True
            return False

    def _update(
        self, set_id: str, *, status: PreparedStatus,
        request_ids: tuple[str, ...] | None = None,
        card_ids: tuple[str, ...] | None = None,
        now: datetime,
    ) -> DatabaseRow:
        coordinator = FlockWriteCoordinator(self.db_path)
        with coordinator.acquire_write_context("multimedia.local_workstation.update") as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_local_prepared_sets WHERE set_id=?", [set_id]
            ).fetchone()
            if row is None or not isinstance(row[10], str) or not hmac.compare_digest(
                row[10], _mac(list(row[:10]), self.signing_key)
            ):
                raise LocalWorkstationError("stored local prepared-set integrity failed")
            values = list(row[:10])
            values[5] = status
            if request_ids is not None:
                values[6] = json.dumps(request_ids, separators=(",", ":"))
            if card_ids is not None:
                values[7] = json.dumps(card_ids, separators=(",", ":"))
            values[9] = _timestamp(now)
            connection.execute(
                "UPDATE multimedia_local_prepared_sets SET status=?, request_ids_json=?, "
                "card_ids_json=?, updated_at=?, row_mac=? WHERE set_id=?",
                [values[5], values[6], values[7], values[9],
                 _mac(values, self.signing_key), set_id],
            )
        return tuple([*values, _mac(values, self.signing_key)])

    def _verify_row(
        self, row: DatabaseRow, owner_digest: str, asset_id: str,
        revision_id: str, plan_digest: str,
    ) -> None:
        if (
            row is None or len(row) != 11
            or list(row[1:5]) != [owner_digest, asset_id, revision_id, plan_digest]
            or not isinstance(row[10], str)
            or not hmac.compare_digest(row[10], _mac(list(row[:10]), self.signing_key))
        ):
            raise LocalWorkstationError("stored local prepared-set integrity failed")


def _set_id(owner_digest: str, asset_id: str, revision_id: str, plan_digest: str) -> str:
    return "mmlocalset_" + hashlib.sha256(
        f"{owner_digest}\0{asset_id}\0{revision_id}\0{plan_digest}".encode()
    ).hexdigest()


def _ids(value: str) -> tuple[str, ...]:
    try:
        rows = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        raise LocalWorkstationError("stored local prepared-set identifiers are invalid") from None
    if not isinstance(rows, list) or len(rows) > 64 or any(not isinstance(row, str) for row in rows):
        raise LocalWorkstationError("stored local prepared-set identifiers are invalid")
    return tuple(rows)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _mac(values: list[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local workstation timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clock(factory: Callable[[], datetime]) -> datetime:
    value = factory()
    if not isinstance(value, datetime):
        raise ValueError("local workstation clock is invalid")
    return value


def _read_private_png(path: str, expected_digest: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise LocalWorkstationError("local source card is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not 32 <= info.st_size <= 16 * 1024 * 1024
        ):
            raise LocalWorkstationError("local source card is unavailable")
        payload = b""
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise LocalWorkstationError("local source card is unavailable")
            payload += chunk
            remaining -= len(chunk)
        if (
            payload[:8] != b"\x89PNG\r\n\x1a\n"
            or not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_digest)
        ):
            raise LocalWorkstationError("local source card is unavailable")
        return payload
    finally:
        os.close(descriptor)


__all__ = [
    "LocalPreparedChapter", "LocalPreparedSet", "LocalWorkstationError",
    "LocalWorkstationRuntime",
]
