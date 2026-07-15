"""Immutable canonical merge drafts and exact owner-bound reviews."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import ValidationError

from runtime.db_lock import connect_read, connect_write
from services.html_projection.canonical_merge import (
    POLICY,
    VERSION,
    CanonicalMember,
    CanonicalMergeError,
    canonicalize_members,
)
from substrate.contracts.html_projection import HtmlProjectionContract

ACKNOWLEDGEMENT_VERSION: Final = "DERIVED_ASSET_MERGE_ACK_V1"
MAX_STORED_HTML_BYTES: Final = 2 * 1024 * 1024


class MergeDraftError(ValueError):
    """Stable fail-closed draft/review error."""


class MergeDraftNotFound(KeyError):
    """The owner-scoped opaque record does not exist."""


@dataclass(frozen=True)
class Draft:
    draft_id: str
    canonical_html: str
    canonical_sha256: str
    manifest_json: str
    manifest_sha256: str
    sanitizer_policy: str
    sanitizer_version: str


@dataclass(frozen=True)
class Review:
    review_id: str
    draft_id: str
    canonical_sha256: str
    manifest_sha256: str
    acknowledgement_version: str


class MergeDraftRepository:
    def __init__(self, *, db_path: str, projection_root: Path) -> None:
        self._db_path = db_path
        self._projection_root = projection_root

    def create_draft(
        self,
        *,
        owner_user_id: str,
        projection_ids: tuple[str, ...],
        intent: Literal["create", "revise"],
        title: str,
        asset_kind: Literal["document", "analysis", "synthesis", "composite"],
        target_asset_id: str | None = None,
        expected_parent_revision_id: str | None = None,
        expected_parent_sha256: str | None = None,
    ) -> Draft:
        if not owner_user_id or not title or not projection_ids:
            raise MergeDraftError("required draft identity is missing")
        if intent == "create":
            if any((target_asset_id, expected_parent_revision_id, expected_parent_sha256)):
                raise MergeDraftError("create intent cannot name a target or parent")
        elif not all((target_asset_id, expected_parent_revision_id, expected_parent_sha256)):
            raise MergeDraftError("revise intent requires exact target parent proof")
        if intent == "revise":
            self._prove_target_authority(
                owner_user_id=owner_user_id,
                target_asset_id=str(target_asset_id),
                expected_parent_revision_id=str(expected_parent_revision_id),
                expected_parent_sha256=str(expected_parent_sha256),
            )
        projections = self._load_projections(projection_ids, owner_user_id=owner_user_id)
        members = tuple(self._load_member(item) for item in projections)
        try:
            canonical = canonicalize_members(members)
        except CanonicalMergeError as exc:
            raise MergeDraftError(str(exc)) from exc
        manifest = _canonical_json(
            [
                {
                    "converter_id": item.converter_id,
                    "converter_version": item.converter_version,
                    "hosted_html_sha256": item.hosted_html_sha256,
                    "member_index": index,
                    "projection_id": item.projection_id,
                    "projection_sanitizer_policy": item.sanitizer_policy,
                    "projection_sanitizer_version": item.sanitizer_version,
                    "source_asset_id": item.source_asset_id,
                    "source_document_id": item.source_document_id,
                    "source_sha256": item.source_sha256,
                }
                for index, item in enumerate(projections)
            ]
        )
        manifest_hash = hashlib.sha256(manifest.encode()).hexdigest()
        draft_id = "drf_" + uuid.uuid4().hex
        with connect_write(self._db_path, purpose="create-derived-asset-merge-draft") as con:
            if intent == "revise" and not self._target_matches(
                con,
                owner_user_id=owner_user_id,
                target_asset_id=str(target_asset_id),
                expected_parent_revision_id=str(expected_parent_revision_id),
                expected_parent_sha256=str(expected_parent_sha256),
            ):
                raise MergeDraftError("target asset or expected parent is unavailable")
            con.execute(
                "INSERT INTO derived_asset_merge_drafts (draft_id, owner_user_id, intent, "
                "target_asset_id, expected_parent_revision_id, expected_parent_sha256, title, "
                "asset_kind, canonical_html, canonical_byte_count, canonical_sha256, manifest_json, "
                "manifest_sha256, sanitizer_policy, sanitizer_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    draft_id,
                    owner_user_id,
                    intent,
                    target_asset_id,
                    expected_parent_revision_id,
                    expected_parent_sha256,
                    title,
                    asset_kind,
                    canonical.html,
                    canonical.byte_count,
                    canonical.sha256,
                    manifest,
                    manifest_hash,
                    POLICY,
                    VERSION,
                ],
            )
        return Draft(
            draft_id, canonical.html, canonical.sha256, manifest, manifest_hash, POLICY, VERSION
        )

    def create_review(self, *, owner_user_id: str, draft_id: str) -> Review:
        with connect_write(self._db_path, purpose="review-derived-asset-merge-draft") as con:
            row = con.execute(
                "SELECT canonical_sha256, manifest_sha256, sanitizer_policy, sanitizer_version, "
                "canonical_html, manifest_json "
                "FROM derived_asset_merge_drafts WHERE draft_id=? AND owner_user_id=?",
                [draft_id, owner_user_id],
            ).fetchone()
            if row is None:
                raise MergeDraftNotFound(draft_id)
            existing = con.execute(
                "SELECT review_id, canonical_sha256, manifest_sha256, acknowledgement_version "
                "FROM derived_asset_merge_reviews WHERE draft_id=? AND owner_user_id=?",
                [draft_id, owner_user_id],
            ).fetchone()
            if existing is not None:
                return Review(
                    str(existing[0]),
                    draft_id,
                    str(existing[1]),
                    str(existing[2]),
                    str(existing[3]),
                )
            target = con.execute(
                "SELECT intent, target_asset_id, expected_parent_revision_id, "
                "expected_parent_sha256 FROM derived_asset_merge_drafts "
                "WHERE draft_id=? AND owner_user_id=?",
                [draft_id, owner_user_id],
            ).fetchone()
            if target is None:
                raise MergeDraftNotFound(draft_id)
            if str(target[0]) == "revise" and not self._target_matches(
                con,
                owner_user_id=owner_user_id,
                target_asset_id=str(target[1]),
                expected_parent_revision_id=str(target[2]),
                expected_parent_sha256=str(target[3]),
            ):
                raise MergeDraftError("target asset or expected parent drifted before review")
            self._prove_exact_draft(con, row, owner_user_id=owner_user_id)
            review_id = "rvw_" + uuid.uuid4().hex
            con.execute(
                "INSERT INTO derived_asset_merge_reviews (review_id, draft_id, owner_user_id, "
                "canonical_sha256, manifest_sha256, sanitizer_policy, sanitizer_version, "
                "acknowledgement_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [review_id, draft_id, owner_user_id, *row[:4], ACKNOWLEDGEMENT_VERSION],
            )
        return Review(review_id, draft_id, str(row[0]), str(row[1]), ACKNOWLEDGEMENT_VERSION)

    def _prove_exact_draft(self, con: Any, row: tuple[Any, ...], *, owner_user_id: str) -> None:
        if (str(row[2]), str(row[3])) != (POLICY, VERSION):
            raise MergeDraftError("canonical policy drifted before review")
        manifest_text = str(row[5])
        try:
            manifest = json.loads(manifest_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise MergeDraftError("draft manifest drifted before review") from exc
        if not isinstance(manifest, list) or _canonical_json(manifest) != manifest_text:
            raise MergeDraftError("draft manifest drifted before review")
        projections: list[HtmlProjectionContract] = []
        for expected_index, entry in enumerate(manifest):
            if not isinstance(entry, dict) or entry.get("member_index") != expected_index:
                raise MergeDraftError("draft manifest drifted before review")
            projection_id = entry.get("projection_id")
            if not isinstance(projection_id, str):
                raise MergeDraftError("draft manifest drifted before review")
            stored = con.execute(
                "SELECT projection_json FROM html_projections WHERE projection_id=?",
                [projection_id],
            ).fetchone()
            if stored is None:
                raise MergeDraftError("projection drifted before review")
            try:
                item = HtmlProjectionContract.model_validate_json(str(stored[0]))
            except ValidationError as exc:
                raise MergeDraftError("projection drifted before review") from exc
            expected = {
                "converter_id": item.converter_id,
                "converter_version": item.converter_version,
                "hosted_html_sha256": item.hosted_html_sha256,
                "member_index": expected_index,
                "projection_id": item.projection_id,
                "projection_sanitizer_policy": item.sanitizer_policy,
                "projection_sanitizer_version": item.sanitizer_version,
                "source_asset_id": item.source_asset_id,
                "source_document_id": item.source_document_id,
                "source_sha256": item.source_sha256,
            }
            if item.status != "ready" or entry != expected:
                raise MergeDraftError("projection drifted before review")
            if not self._projection_owned(con, item=item, owner_user_id=owner_user_id):
                raise MergeDraftError("projection drifted before review")
            projections.append(item)
        canonical = canonicalize_members(tuple(self._load_member(item) for item in projections))
        if canonical.html != str(row[4]) or canonical.sha256 != str(row[0]):
            raise MergeDraftError("canonical bytes drifted before review")
        if hashlib.sha256(manifest_text.encode()).hexdigest() != str(row[1]):
            raise MergeDraftError("draft manifest drifted before review")

    def load_preview(self, *, owner_user_id: str, opaque_id: str) -> Draft:
        join = ""
        params: list[str] = [opaque_id, owner_user_id]
        predicate = "d.draft_id=? AND d.owner_user_id=?"
        if opaque_id.startswith("rvw_"):
            join = (
                " JOIN derived_asset_merge_reviews r ON r.draft_id=d.draft_id "
                "AND r.owner_user_id=d.owner_user_id "
                "AND r.canonical_sha256=d.canonical_sha256 "
                "AND r.manifest_sha256=d.manifest_sha256 "
                "AND r.sanitizer_policy=d.sanitizer_policy "
                "AND r.sanitizer_version=d.sanitizer_version "
            )
            predicate = "r.review_id=? AND r.owner_user_id=?"
        with connect_read(self._db_path) as con:
            row = con.execute(
                "SELECT d.draft_id, d.canonical_html, d.canonical_sha256, d.manifest_json, "
                "d.manifest_sha256, d.sanitizer_policy, d.sanitizer_version "
                "FROM derived_asset_merge_drafts d" + join + " WHERE " + predicate,
                params,
            ).fetchone()
        if row is None:
            raise MergeDraftNotFound(opaque_id)
        draft = Draft(*(str(value) for value in row))
        if hashlib.sha256(draft.canonical_html.encode()).hexdigest() != draft.canonical_sha256:
            raise MergeDraftError("stored canonical draft drifted")
        if hashlib.sha256(draft.manifest_json.encode()).hexdigest() != draft.manifest_sha256:
            raise MergeDraftError("stored draft manifest drifted")
        if (draft.sanitizer_policy, draft.sanitizer_version) != (POLICY, VERSION):
            raise MergeDraftError("stored canonical policy drifted")
        return draft

    def _load_projections(
        self, projection_ids: tuple[str, ...], *, owner_user_id: str
    ) -> tuple[HtmlProjectionContract, ...]:
        if len(set(projection_ids)) != len(projection_ids):
            raise MergeDraftError("projection IDs must be unique")
        with connect_read(self._db_path) as con:
            result = []
            for projection_id in projection_ids:
                row = con.execute(
                    "SELECT projection_json FROM html_projections WHERE projection_id=?",
                    [projection_id],
                ).fetchone()
                if row is None:
                    raise MergeDraftError("projection is not ready")
                try:
                    item = HtmlProjectionContract.model_validate_json(str(row[0]))
                except ValidationError as exc:
                    raise MergeDraftError("projection is not ready") from exc
                if item.status != "ready":
                    raise MergeDraftError("projection is not ready")
                if not self._projection_owned(con, item=item, owner_user_id=owner_user_id):
                    raise MergeDraftError("projection is not ready")
                result.append(item)
        return tuple(result)

    def _load_member(self, item: HtmlProjectionContract) -> CanonicalMember:
        locator = item.hosted_html_locator
        expected = item.hosted_html_sha256
        if locator is None or expected is None:
            raise MergeDraftError("projection is not ready")
        if not self._projection_root.is_absolute():
            raise MergeDraftError("projection root is unsafe")
        try:
            root_metadata = self._projection_root.lstat()
            root = self._projection_root.resolve(strict=True)
        except OSError as exc:
            raise MergeDraftError("projection root is unavailable") from exc
        if self._projection_root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise MergeDraftError("projection root is unsafe")
        candidate = self._projection_root.joinpath(*locator.split("/"))
        try:
            path_cursor = self._projection_root
            for component in locator.split("/"):
                path_cursor = path_cursor / component
                if path_cursor.is_symlink():
                    raise MergeDraftError("projection object is unsafe")
            metadata = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise MergeDraftError("projection object is unavailable") from exc
        if (
            candidate.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not resolved.is_relative_to(root)
        ):
            raise MergeDraftError("projection object is unsafe")
        if metadata.st_size > MAX_STORED_HTML_BYTES:
            raise MergeDraftError("projection object is oversized")
        try:
            descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                current = os.fstat(descriptor)
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                        or (current.st_dev, current.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                )):
                    raise MergeDraftError("projection object changed during load")
                chunks: list[bytes] = []
                remaining = MAX_STORED_HTML_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 64 * 1024))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise MergeDraftError("projection object is unavailable") from exc
        if len(data) > MAX_STORED_HTML_BYTES or hashlib.sha256(data).hexdigest() != expected:
            raise MergeDraftError("projection object hash drifted")
        return CanonicalMember(
            item.projection_id,
            item.source_asset_id,
            item.source_document_id,
            item.source_sha256,
            expected,
            data,
        )

    def _prove_target_authority(
        self,
        *,
        owner_user_id: str,
        target_asset_id: str,
        expected_parent_revision_id: str,
        expected_parent_sha256: str,
    ) -> None:
        """Bind revise intent to the owner's exact current revision.

        The request may name an intended target, but it cannot manufacture
        ownership or parent authority. Missing, foreign, and stale targets use
        one refusal so this pre-commit review surface does not enumerate assets.
        """
        with connect_read(self._db_path) as con:
            matched = self._target_matches(
                con,
                owner_user_id=owner_user_id,
                target_asset_id=target_asset_id,
                expected_parent_revision_id=expected_parent_revision_id,
                expected_parent_sha256=expected_parent_sha256,
            )
        if not matched:
            raise MergeDraftError("target asset or expected parent is unavailable")

    @staticmethod
    def _target_matches(
        con: Any,
        *,
        owner_user_id: str,
        target_asset_id: str,
        expected_parent_revision_id: str,
        expected_parent_sha256: str,
    ) -> bool:
        row = con.execute(
            "SELECT c.current_revision_id, c.current_content_sha256 "
            "FROM derived_assets a JOIN derived_asset_current_revisions c "
            "ON c.derived_asset_id=a.derived_asset_id "
            "WHERE a.derived_asset_id=? AND a.owner_user_id=?",
            [target_asset_id, owner_user_id],
        ).fetchone()
        return bool(row == (expected_parent_revision_id, expected_parent_sha256))

    @staticmethod
    def _document_owned(con: Any, *, document_id: str, owner_user_id: str) -> bool:
        row = con.execute(
            "SELECT 1 FROM documents WHERE document_id=? AND owner_user_id=?",
            [document_id, owner_user_id],
        ).fetchone()
        return bool(row == (1,))

    def _projection_owned(
        self, con: Any, *, item: HtmlProjectionContract, owner_user_id: str
    ) -> bool:
        if self._document_owned(
            con, document_id=item.source_document_id, owner_user_id=owner_user_id
        ):
            return True
        prefix = "twin-note-merge-bridge:"
        if not item.source_document_id.startswith(prefix):
            return False
        bridge_id = item.source_document_id.removeprefix(prefix)
        # The current read connection remains authoritative for ordinary documents.
        # Bridge ownership additionally requires a complete immutable receipt reopen.
        from substrate.twin_note_taker.merge_bridge import (
            MergeBridgeIntegrity,
            MergeBridgeUnavailable,
            TwinNoteMergeBridge,
        )

        try:
            result = TwinNoteMergeBridge(
                db_path=self._db_path, publication_root=self._projection_root
            ).reopen(owner_user_id=owner_user_id, bridge_id=bridge_id, con=con)
        except (MergeBridgeIntegrity, MergeBridgeUnavailable):
            return False
        return result.projection_id == item.projection_id


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "ACKNOWLEDGEMENT_VERSION",
    "Draft",
    "MergeDraftError",
    "MergeDraftNotFound",
    "MergeDraftRepository",
    "Review",
]
