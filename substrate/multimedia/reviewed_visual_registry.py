"""Owner-bound reviewed visual authority for later documentary production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .read_model import MultimediaAssetRecord, MultimediaAssetStore
from .visual_selection import ReviewedVisualSelection

_MAX_FILE_BYTES = 100 * 1024 * 1024
_COPY_BYTES = 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_OWNER = re.compile(r"^[0-9a-f]{64}$")

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_reviewed_visual_sets (
    owner_identity_digest TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    set_id TEXT NOT NULL,
    candidate_ids_json TEXT NOT NULL,
    selections_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    registry_mac TEXT NOT NULL,
    PRIMARY KEY (owner_identity_digest, asset_id, revision_id),
    UNIQUE (owner_identity_digest, request_id)
)
"""


class ReviewedVisualRegistryError(RuntimeError):
    """A reviewed visual set is unavailable, stale, or conflicting."""


@dataclass(frozen=True)
class VisualCandidateBinding:
    chapter_id: str
    candidate_id: str


@dataclass(frozen=True)
class RegisterReviewedVisualsRequest:
    request_id: str
    expected_revision_id: str
    bindings: tuple[VisualCandidateBinding, ...]


@dataclass(frozen=True)
class ReviewedVisualSetReceipt:
    set_id: str
    asset_id: str
    revision_id: str
    chapter_ids: tuple[str, ...]
    scene_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    selection_digest: str
    created_at: str


@dataclass(frozen=True)
class ResolvedReviewedVisualSet:
    receipt: ReviewedVisualSetReceipt
    selections: tuple[ReviewedVisualSelection, ...]


class VisualCandidateResolver(Protocol):
    def __call__(
        self,
        record: MultimediaAssetRecord,
        owner_id: str,
        chapter_id: str,
        candidate_id: str,
    ) -> ReviewedVisualSelection: ...


class ReviewedVisualRegistry:
    def __init__(self, *, db_path: str, integrity_key: bytes) -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path is required")
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise ValueError("integrity_key must contain at least 32 bytes")
        self._db_path = db_path
        self._integrity_key = integrity_key

    def assert_independent_snapshot_key(self, snapshot_key: bytes) -> None:
        """Reject reuse of the key authenticating reviewed visual selections."""
        if not isinstance(snapshot_key, bytes) or len(snapshot_key) < 32:
            raise ValueError("production snapshot key is invalid")
        if hmac.compare_digest(snapshot_key, self._integrity_key):
            raise ValueError("production snapshot key must be independent")

    def register(
        self,
        *,
        owner_identity_digest: str,
        asset_id: str,
        revision_id: str,
        request_id: str,
        candidate_ids: tuple[str, ...],
        selections: tuple[ReviewedVisualSelection, ...],
        now: datetime,
    ) -> ResolvedReviewedVisualSet:
        if not _OWNER.fullmatch(owner_identity_digest):
            raise ValueError("owner identity digest is invalid")
        for name, value in (
            ("asset_id", asset_id),
            ("revision_id", revision_id),
            ("request_id", request_id),
        ):
            _identifier(value, name)
        if not selections or len(selections) > 64 or len(candidate_ids) != len(selections):
            raise ValueError("reviewed visual set must contain one through 64 selections")
        for candidate_id in candidate_ids:
            _identifier(candidate_id, "candidate_id")
        selections_json = _selections_json(selections)
        candidate_ids_json = _canonical_json(list(candidate_ids))
        selection_digest = hashlib.sha256(selections_json.encode("ascii")).hexdigest()
        request_hash = hashlib.sha256(
            _canonical_json(
                {
                    "asset_id": asset_id,
                    "candidate_ids": list(candidate_ids),
                    "revision_id": revision_id,
                    "selection_digest": selection_digest,
                }
            ).encode("ascii")
        ).hexdigest()
        set_id = "mmvset_" + hashlib.sha256(
            f"{owner_identity_digest}\0{asset_id}\0{revision_id}\0{selection_digest}".encode()
        ).hexdigest()
        created_at = _timestamp(now)
        values = {
            "asset_id": asset_id,
            "candidate_ids_json": candidate_ids_json,
            "created_at": created_at,
            "owner_identity_digest": owner_identity_digest,
            "request_hash": request_hash,
            "request_id": request_id,
            "revision_id": revision_id,
            "selections_json": selections_json,
            "set_id": set_id,
        }
        registry_mac = _mac(values, self._integrity_key)
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.reviewed_visuals.register") as ctx:
            ctx.execute(_DDL)
            ctx.execute("BEGIN TRANSACTION")
            try:
                by_request = ctx.execute(
                    "SELECT * FROM multimedia_reviewed_visual_sets "
                    "WHERE owner_identity_digest=? AND request_id=?",
                    [owner_identity_digest, request_id],
                ).fetchone()
                if by_request is not None:
                    reopened = self._decode(by_request)
                    if str(by_request[4]) != request_hash:
                        raise ReviewedVisualRegistryError(
                            "reviewed visual request id already has different terms"
                        )
                    ctx.execute("COMMIT")
                    return reopened
                existing = ctx.execute(
                    "SELECT * FROM multimedia_reviewed_visual_sets "
                    "WHERE owner_identity_digest=? AND asset_id=? AND revision_id=?",
                    [owner_identity_digest, asset_id, revision_id],
                ).fetchone()
                if existing is not None:
                    self._decode(existing)
                    raise ReviewedVisualRegistryError(
                        "reviewed visual set already exists for this revision"
                    )
                ctx.execute(
                    "INSERT INTO multimedia_reviewed_visual_sets VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        owner_identity_digest,
                        asset_id,
                        revision_id,
                        request_id,
                        request_hash,
                        set_id,
                        candidate_ids_json,
                        selections_json,
                        created_at,
                        registry_mac,
                    ],
                )
            except Exception:
                ctx.execute("ROLLBACK")
                raise
            else:
                ctx.execute("COMMIT")
        return self.get(
            owner_identity_digest=owner_identity_digest,
            asset_id=asset_id,
            revision_id=revision_id,
        )

    def get(
        self, *, owner_identity_digest: str, asset_id: str, revision_id: str
    ) -> ResolvedReviewedVisualSet:
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.reviewed_visuals.get") as ctx:
            ctx.execute(_DDL)
            row = ctx.execute(
                "SELECT * FROM multimedia_reviewed_visual_sets "
                "WHERE owner_identity_digest=? AND asset_id=? AND revision_id=?",
                [owner_identity_digest, asset_id, revision_id],
            ).fetchone()
        if row is None:
            raise ReviewedVisualRegistryError("reviewed visual set is unavailable")
        return self._decode(row)

    def get_existing(
        self, *, owner_identity_digest: str, asset_id: str, revision_id: str
    ) -> ResolvedReviewedVisualSet:
        """Read an existing reviewed set without schema creation or a write lock."""
        if not Path(self._db_path).is_file():
            raise ReviewedVisualRegistryError("reviewed visual set is unavailable")
        try:
            with connect_read(self._db_path) as connection:
                row = connection.execute(
                    "SELECT * FROM multimedia_reviewed_visual_sets "
                    "WHERE owner_identity_digest=? AND asset_id=? AND revision_id=?",
                    [owner_identity_digest, asset_id, revision_id],
                ).fetchone()
        except Exception as exc:
            raise ReviewedVisualRegistryError(
                "reviewed visual set is unavailable"
            ) from exc
        if row is None:
            raise ReviewedVisualRegistryError("reviewed visual set is unavailable")
        return self._decode(tuple(row))

    def _decode(self, row: tuple[object, ...]) -> ResolvedReviewedVisualSet:
        if len(row) != 10 or not all(isinstance(value, str) for value in row):
            raise ReviewedVisualRegistryError("stored reviewed visual set is malformed")
        values = {
            "owner_identity_digest": row[0],
            "asset_id": row[1],
            "revision_id": row[2],
            "request_id": row[3],
            "request_hash": row[4],
            "set_id": row[5],
            "candidate_ids_json": row[6],
            "selections_json": row[7],
            "created_at": row[8],
        }
        if not hmac.compare_digest(str(row[9]), _mac(values, self._integrity_key)):
            raise ReviewedVisualRegistryError("stored reviewed visual set MAC is invalid")
        try:
            raw_candidates = json.loads(str(row[6]))
            raw_selections = json.loads(str(row[7]))
            if not isinstance(raw_candidates, list) or not isinstance(raw_selections, list):
                raise ValueError
            candidate_ids = tuple(str(value) for value in raw_candidates)
            selections = tuple(
                ReviewedVisualSelection.model_validate(value) for value in raw_selections
            )
        except (TypeError, ValueError) as exc:
            raise ReviewedVisualRegistryError("stored reviewed visual set is malformed") from exc
        if not selections or len(candidate_ids) != len(selections):
            raise ReviewedVisualRegistryError("stored reviewed visual set is incomplete")
        for selection in selections:
            digest = _regular_file_digest(selection.path)
            if not hmac.compare_digest(digest, selection.expected_sha256):
                raise ReviewedVisualRegistryError("reviewed visual file changed after review")
        selection_digest = hashlib.sha256(str(row[7]).encode("ascii")).hexdigest()
        expected_set = "mmvset_" + hashlib.sha256(
            f"{row[0]}\0{row[1]}\0{row[2]}\0{selection_digest}".encode()
        ).hexdigest()
        if not hmac.compare_digest(str(row[5]), expected_set):
            raise ReviewedVisualRegistryError("stored reviewed visual identity conflicts")
        chapter_ids = tuple(
            _chapter_from_scene(selection.scene_id) for selection in selections
        )
        receipt = ReviewedVisualSetReceipt(
            set_id=str(row[5]),
            asset_id=str(row[1]),
            revision_id=str(row[2]),
            chapter_ids=chapter_ids,
            scene_ids=tuple(selection.scene_id for selection in selections),
            candidate_ids=candidate_ids,
            selection_digest=selection_digest,
            created_at=str(row[8]),
        )
        return ResolvedReviewedVisualSet(receipt=receipt, selections=selections)


def register_reviewed_visuals(
    asset_id: str,
    request: RegisterReviewedVisualsRequest,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    registry: ReviewedVisualRegistry,
    candidate_resolver: VisualCandidateResolver,
    clock: Callable[[], datetime],
) -> ReviewedVisualSetReceipt:
    record = _record(asset_id, owner_id, store)
    if record.asset.revision_id != request.expected_revision_id:
        raise ReviewedVisualRegistryError("multimedia visual revision is not current")
    if str(record.asset.status) != "ready":
        raise ReviewedVisualRegistryError("reviewed visuals require a ready asset")
    if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
        raise ReviewedVisualRegistryError("reviewed visuals require a video asset")
    if record.asset.route_policy == "cheapest":
        raise ReviewedVisualRegistryError("cheapest route cannot select production visuals")
    chapters = tuple(
        chapter
        for chapter in record.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in record.plan.script_lines
        )
    )
    if tuple(binding.chapter_id for binding in request.bindings) != tuple(
        chapter.chapter_id for chapter in chapters
    ):
        raise ReviewedVisualRegistryError("visual candidates must cover spoken chapters in order")
    candidate_ids = tuple(binding.candidate_id for binding in request.bindings)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ReviewedVisualRegistryError("visual candidate ids must be unique")
    selections: list[ReviewedVisualSelection] = []
    try:
        for chapter, binding in zip(chapters, request.bindings, strict=True):
            selection = ReviewedVisualSelection.model_validate(
                candidate_resolver(
                    record, owner_id, chapter.chapter_id, binding.candidate_id
                ).model_dump(mode="python")
            )
            scenes = tuple(
                row
                for row in record.plan.scenes
                if row.chapter_id == chapter.chapter_id and row.scene_id == selection.scene_id
            )
            if len(scenes) != 1:
                raise ReviewedVisualRegistryError("visual candidate scene conflicts")
            if selection.source_chunk_ids != chapter.source_chunk_ids:
                raise ReviewedVisualRegistryError("visual candidate grounding conflicts")
            digest = _regular_file_digest(selection.path)
            if not hmac.compare_digest(digest, selection.expected_sha256):
                raise ReviewedVisualRegistryError("visual candidate digest conflicts")
            selections.append(selection)
    except ReviewedVisualRegistryError:
        raise
    except (KeyError, LookupError, OSError, TypeError, ValueError) as exc:
        raise ReviewedVisualRegistryError("visual candidate is unavailable") from exc
    current = _record(asset_id, owner_id, store)
    if current.asset.revision_id != request.expected_revision_id:
        raise ReviewedVisualRegistryError("multimedia visual revision changed during review")
    receipt = registry.register(
        owner_identity_digest=record.asset.owner_user_id,
        asset_id=asset_id,
        revision_id=request.expected_revision_id,
        request_id=request.request_id,
        candidate_ids=candidate_ids,
        selections=tuple(selections),
        now=clock(),
    ).receipt
    final = _record(asset_id, owner_id, store)
    if final.asset.revision_id != request.expected_revision_id:
        raise ReviewedVisualRegistryError("multimedia visual revision changed during review")
    return replace(receipt, chapter_ids=tuple(row.chapter_id for row in chapters))


def get_reviewed_visuals(
    asset_id: str,
    revision_id: str,
    *,
    owner_id: str,
    store: MultimediaAssetStore,
    registry: ReviewedVisualRegistry,
) -> ResolvedReviewedVisualSet:
    record = _record(asset_id, owner_id, store)
    if record.asset.revision_id != revision_id:
        raise ReviewedVisualRegistryError("reviewed visual set is unavailable")
    resolved = registry.get(
        owner_identity_digest=record.asset.owner_user_id,
        asset_id=asset_id,
        revision_id=revision_id,
    )
    chapter_ids: list[str] = []
    for selection in resolved.selections:
        matches = tuple(
            chapter.chapter_id
            for chapter in record.plan.chapters
            if tuple(chapter.source_chunk_ids) == tuple(selection.source_chunk_ids)
            and (
                any(
                    scene.scene_id == selection.scene_id
                    and scene.chapter_id == chapter.chapter_id
                    for scene in record.plan.scenes
                )
                or selection.scene_id == f"scene-{chapter.chapter_id}"
            )
        )
        if len(matches) != 1:
            raise ReviewedVisualRegistryError("reviewed visual chapter binding is unavailable")
        chapter_ids.append(matches[0])
    return replace(
        resolved,
        receipt=replace(resolved.receipt, chapter_ids=tuple(chapter_ids)),
    )


def _record(
    asset_id: str, owner_id: str, store: MultimediaAssetStore
) -> MultimediaAssetRecord:
    try:
        return store.get(asset_id, owner_id=owner_id)
    except (KeyError, ValueError) as exc:
        raise ReviewedVisualRegistryError("multimedia asset is unavailable") from exc


def _selections_json(selections: tuple[ReviewedVisualSelection, ...]) -> str:
    return _canonical_json([selection.model_dump(mode="json") for selection in selections])


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _mac(values: Mapping[str, object], key: bytes) -> str:
    return hmac.new(key, _canonical_json(values).encode("ascii"), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _chapter_from_scene(scene_id: str) -> str:
    if not scene_id.startswith("scene-") or len(scene_id) <= 6:
        raise ReviewedVisualRegistryError("stored reviewed visual scene is malformed")
    return scene_id[6:]


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _regular_file_digest(path: str) -> str:
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ReviewedVisualRegistryError("visual candidate is not a regular file")
        if before.st_size <= 0 or before.st_size > _MAX_FILE_BYTES:
            raise ReviewedVisualRegistryError("visual candidate exceeds its byte ceiling")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReviewedVisualRegistryError("visual candidate is unavailable") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ReviewedVisualRegistryError("visual candidate changed during review")
        total = 0
        while chunk := os.read(fd, _COPY_BYTES):
            total += len(chunk)
            if total > _MAX_FILE_BYTES:
                raise ReviewedVisualRegistryError("visual candidate exceeds its byte ceiling")
            digest.update(chunk)
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise ReviewedVisualRegistryError("visual candidate changed during review")
    finally:
        os.close(fd)
    return digest.hexdigest()


__all__ = [
    "RegisterReviewedVisualsRequest",
    "ResolvedReviewedVisualSet",
    "ReviewedVisualRegistry",
    "ReviewedVisualRegistryError",
    "ReviewedVisualSetReceipt",
    "VisualCandidateBinding",
    "VisualCandidateResolver",
    "get_reviewed_visuals",
    "register_reviewed_visuals",
]
