"""Owner-scoped read model for the twin-note canonical merge workstation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from runtime.db_lock import connect_read
from substrate.contracts.html_projection import HtmlProjectionContract
from substrate.research_artifact.merge_draft import MergeDraftError, MergeDraftRepository

from .merge_bridge import MergeBridgeIntegrity, parse_public_note
from .serving import TwinNoteIntegrityError, TwinNoteServingService, TwinNoteUnavailable

MAX_SOURCE_PROJECTIONS = 200
MAX_TWIN_SOURCES = 400
MAX_CONTEXT_NOTES = 1_000


class MergeContextUnavailable(LookupError):
    pass


class MergeContextIntegrity(RuntimeError):
    pass


class TwinNoteMergeContext:
    def __init__(self, *, db_path: str, projection_root: Path) -> None:
        if not projection_root.is_absolute():
            raise ValueError("projection_root must be absolute")
        self.db_path = db_path
        self.repository = MergeDraftRepository(db_path=db_path, projection_root=projection_root)
        self.serving = TwinNoteServingService(db_path=db_path)

    def discover(self, owner_user_id: str) -> dict[str, Any]:
        if not owner_user_id:
            raise MergeContextUnavailable
        with connect_read(self.db_path) as con:
            projection_rows = con.execute(
                "SELECT h.projection_id,h.projection_json,h.identity_json,d.title FROM html_projections h "
                "JOIN documents d ON (json_extract_string(h.projection_json,'$.source_document_id')="
                "d.document_id OR json_extract_string(h.identity_json,'$.source_document_id')="
                "d.document_id) WHERE d.owner_user_id=? ORDER BY h.projection_id LIMIT ?",
                [owner_user_id, MAX_SOURCE_PROJECTIONS + 1],
            ).fetchall()
            if len(projection_rows) > MAX_SOURCE_PROJECTIONS:
                raise MergeContextIntegrity
            projections = [
                self._projection(con, owner_user_id, str(row_id), str(raw), str(identity), title)
                for row_id, raw, identity, title in projection_rows
            ]

            revision_ids = con.execute(
                "SELECT revision_id FROM twin_note_revisions WHERE account_id=? "
                "ORDER BY asset_id,created_at,revision_id LIMIT ?",
                [owner_user_id, MAX_TWIN_SOURCES + 1],
            ).fetchall()
            composition_ids = con.execute(
                "SELECT composition_id FROM twin_note_compositions WHERE account_id=? "
                "ORDER BY created_at,composition_id LIMIT ?",
                [owner_user_id, MAX_TWIN_SOURCES + 1],
            ).fetchall()
            if len(revision_ids) + len(composition_ids) > MAX_TWIN_SOURCES:
                raise MergeContextIntegrity

            sources: list[dict[str, Any]] = []
            note_total = 0
            for (revision_id,) in revision_ids:
                revision = self.serving.revision_on(con, owner_user_id, str(revision_id))
                rendered, count = self._revision_response(revision, member_ordinal=None)
                note_total += count
                sources.append({
                    "kind": "revision",
                    "id": revision.revision_id,
                    "label": revision.asset_id,
                    "html_url": f"/research/twin-notes/merge-context/revision/{revision.revision_id}/preview",
                    "revisions": [rendered],
                })
            for (composition_id,) in composition_ids:
                composition = self.serving.verified_composition_on(
                    con, owner_user_id, str(composition_id)
                )
                revisions = []
                for ordinal, revision in enumerate(composition.members):
                    rendered, count = self._revision_response(revision, member_ordinal=ordinal)
                    note_total += count
                    revisions.append(rendered)
                sources.append({
                    "kind": "composition",
                    "id": composition.composition_id,
                    "label": f"Composition ({len(revisions)} revisions)",
                    "html_url": f"/research/twin-notes/merge-context/composition/{composition.composition_id}/preview",
                    "revisions": revisions,
                })
            if note_total > MAX_CONTEXT_NOTES:
                raise MergeContextIntegrity
        return {
            "source_projections": projections,
            "twin_sources": sources,
            "limits": {
                "source_projections": MAX_SOURCE_PROJECTIONS,
                "twin_sources": MAX_TWIN_SOURCES,
                "notes": MAX_CONTEXT_NOTES,
            },
        }

    def source_preview(self, owner_user_id: str, projection_id: str) -> bytes:
        with connect_read(self.db_path) as con:
            row = con.execute(
                "SELECT projection_json,identity_json FROM html_projections WHERE projection_id=?",
                [projection_id],
            ).fetchone()
            if row is None:
                raise MergeContextUnavailable
            projection = self._verified_projection(
                con, owner_user_id, str(row[0]), str(row[1]),
                expected_id=projection_id, foreign_unavailable=True,
            )
            try:
                return self.repository.load_member(projection).html_bytes
            except MergeDraftError as exc:
                raise MergeContextIntegrity from exc

    def twin_preview(self, owner_user_id: str, kind: str, source_id: str) -> bytes:
        try:
            if kind == "revision":
                return self.serving.revision(owner_user_id, source_id).html_bytes
            if kind == "composition":
                return self.serving.composition(owner_user_id, source_id)
        except TwinNoteUnavailable as exc:
            raise MergeContextUnavailable from exc
        except TwinNoteIntegrityError as exc:
            raise MergeContextIntegrity from exc
        raise MergeContextUnavailable

    def _projection(
        self, con: Any, owner_user_id: str, expected_id: str, raw: str,
        identity_raw: str, title: str | None,
    ) -> dict[str, str]:
        projection = self._verified_projection(
            con, owner_user_id, raw, identity_raw, expected_id=expected_id
        )
        try:
            self.repository.load_member(projection)
        except MergeDraftError as exc:
            raise MergeContextIntegrity from exc
        return {
            "projection_id": projection.projection_id,
            "source_asset_id": projection.source_asset_id,
            "source_document_id": projection.source_document_id,
            "label": title.strip() if isinstance(title, str) and title.strip() else projection.source_document_id,
            "preview_url": (
                "/research/twin-notes/merge-context/source-projections/"
                f"{projection.projection_id}/preview"
            ),
        }

    @staticmethod
    def _verified_projection(
        con: Any, owner_user_id: str, raw: str, identity_raw: str,
        *, expected_id: str | None = None, foreign_unavailable: bool = False,
    ) -> HtmlProjectionContract:
        try:
            projection = HtmlProjectionContract.model_validate_json(raw)
            identity = json.loads(identity_raw)
        except (ValidationError, ValueError, TypeError) as exc:
            raise MergeContextIntegrity from exc
        if identity != projection.identity() or (
            expected_id is not None and projection.projection_id != expected_id
        ):
            raise MergeContextIntegrity
        owned = con.execute(
            "SELECT 1 FROM documents WHERE document_id=? AND owner_user_id=?",
            [projection.source_document_id, owner_user_id],
        ).fetchone()
        if owned != (1,):
            if foreign_unavailable:
                raise MergeContextUnavailable
            raise MergeContextIntegrity
        if projection.status != "ready":
            raise MergeContextIntegrity
        return projection

    @staticmethod
    def _revision_response(revision: Any, *, member_ordinal: int | None) -> tuple[dict[str, Any], int]:
        notes = []
        try:
            for ordinal, value in enumerate(revision.body.agent_notes):
                text, source_count = parse_public_note(value)
                notes.append({
                    "note_ordinal": ordinal,
                    "text": text,
                    "source_count": source_count,
                })
        except MergeBridgeIntegrity as exc:
            raise MergeContextIntegrity from exc
        return ({
            "member_ordinal": member_ordinal,
            "revision_id": revision.revision_id,
            "notes": notes,
        }, len(notes))


__all__ = ["MergeContextIntegrity", "MergeContextUnavailable", "TwinNoteMergeContext"]
