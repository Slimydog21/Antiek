"""Owner-bound adapter from verified twin notes to immutable HTML projections."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from runtime.db_lock import connect_read, connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.reading.projection.store import ProjectionStore
from substrate.research_artifact.merge_draft import MergeDraftError, MergeDraftRepository

from .compression import DurableTwinNoteCompression
from .serving import (
    TwinNoteIntegrityError,
    TwinNoteServingService,
    TwinNoteUnavailable,
    VerifiedRevision,
)

BRIDGE_POLICY = "twin-note-merge-bridge"
BRIDGE_VERSION = "1"
MAX_SELECTED_NOTES = 1_000
MAX_APPENDIX_BYTES = 2 * 1024 * 1024


class MergeBridgeUnavailable(LookupError):
    pass


class MergeBridgeConflict(RuntimeError):
    pass


class MergeBridgeIntegrity(RuntimeError):
    pass


@dataclass(frozen=True)
class SelectedNote:
    revision_id: str
    note_ordinal: int


@dataclass(frozen=True)
class MergeBridgeResult:
    projection_id: str
    source_projection_id: str
    twin_source_kind: str
    twin_source_id: str
    member_count: int
    hosted_html_sha256: str

    def response(self) -> dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "source_projection_id": self.source_projection_id,
            "twin_source": {"kind": self.twin_source_kind, "id": self.twin_source_id},
            "member_count": self.member_count,
            "hosted_html_sha256": self.hosted_html_sha256,
            "merge_draft_input": {
                "projection_ids": [self.source_projection_id, self.projection_id]
            },
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class TwinNoteMergeBridge:
    def __init__(self, *, db_path: str, publication_root: Path) -> None:
        if not publication_root.is_absolute():
            raise ValueError("publication_root must be absolute")
        self.db_path = db_path
        self.publication_root = publication_root
        self.serving = TwinNoteServingService(db_path=db_path)
        self.publisher = DurableTwinNoteCompression(
            lambda _owner, _asset, _investigation: False,
            db_path=db_path,
            publication_root=publication_root,
            initialize_schema=False,
        )

    def create(
        self,
        *,
        owner_user_id: str,
        source_projection_id: str,
        source_kind: Literal["revision", "composition"],
        source_id: str,
        selected_notes: Sequence[SelectedNote],
        idempotency_key: str,
    ) -> MergeBridgeResult:
        result = self._create_serialized(
            owner_user_id=owner_user_id,
            source_projection_id=source_projection_id,
            source_kind=source_kind,
            source_id=source_id,
            selected_notes=selected_notes,
            idempotency_key=idempotency_key,
        )
        self.recover(bridge_id=result)
        with connect_write(self.db_path, purpose="twin_note/merge_bridge_verify") as con:
            return self.reopen(owner_user_id=owner_user_id, bridge_id=result, con=con)

    def _create_serialized(
        self,
        *,
        owner_user_id: str,
        source_projection_id: str,
        source_kind: Literal["revision", "composition"],
        source_id: str,
        selected_notes: Sequence[SelectedNote],
        idempotency_key: str,
    ) -> str:
        if not owner_user_id or not 16 <= len(idempotency_key) <= 128:
            raise MergeBridgeConflict("invalid bridge command")
        if not 1 <= len(selected_notes) <= MAX_SELECTED_NOTES:
            raise MergeBridgeUnavailable
        pairs = [(item.revision_id, item.note_ordinal) for item in selected_notes]
        if len(set(pairs)) != len(pairs) or any(type(note) is not int or note < 0 for _, note in pairs):
            raise MergeBridgeUnavailable
        request_json = _canonical({
            "source_projection_id": source_projection_id,
            "source": {"kind": source_kind, "id": source_id},
            "selected_notes": [
                {"revision_id": revision, "note_ordinal": ordinal} for revision, ordinal in pairs
            ],
        })
        request_sha = _sha(request_json)
        with connect_write(self.db_path, purpose="twin_note/merge_bridge") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                key_row = con.execute(
                    "SELECT request_sha256 FROM twin_note_merge_bridges "
                    "WHERE owner_user_id=? AND idempotency_key=?",
                    [owner_user_id, idempotency_key],
                ).fetchone()
                if key_row is not None and key_row[0] != request_sha:
                    raise MergeBridgeConflict("idempotency key reuse conflicts")
                semantic = con.execute(
                    "SELECT bridge_id FROM twin_note_merge_bridges "
                    "WHERE owner_user_id=? AND request_sha256=?",
                    [owner_user_id, request_sha],
                ).fetchone()
                if semantic is not None:
                    existing_bridge_id = str(semantic[0])
                    con.execute("ROLLBACK")
                    return existing_bridge_id
                source = self._source_projection(con, owner_user_id, source_projection_id)
                revisions = self._source_revisions(con, owner_user_id, source_kind, source_id)
                by_id = {revision.revision_id: revision for revision in revisions}
                members: list[dict[str, Any]] = []
                rendered: list[tuple[str, int]] = []
                for member_ordinal, (revision_id, note_ordinal) in enumerate(pairs):
                    revision = by_id.get(revision_id)
                    if revision is None or note_ordinal >= len(revision.body.agent_notes):
                        raise MergeBridgeUnavailable
                    note, source_count = self._public_note(revision.body.agent_notes[note_ordinal])
                    members.append({
                        "member_ordinal": member_ordinal,
                        "revision_id": revision_id,
                        "note_ordinal": note_ordinal,
                        "revision_body_sha256": revision.body_sha256,
                        "revision_html_sha256": revision.html_sha256,
                        "canonical_note_sha256": _sha(note),
                    })
                    rendered.append((note, source_count))
                appendix = self._render(rendered)
                if len(appendix) > MAX_APPENDIX_BYTES:
                    raise MergeBridgeConflict("generated appendix exceeds byte ceiling")
                appendix_sha = _sha(appendix)
                bridge_id = "tmb_" + _sha(_canonical([owner_user_id, request_sha]))[:32]
                locator = f"{_sha(owner_user_id)[:24]}/{bridge_id}/appendix.html"
                manifest_json = _canonical({
                    "bridge_policy": BRIDGE_POLICY,
                    "bridge_version": BRIDGE_VERSION,
                    "source_projection_id": source.projection_id,
                    "source_asset_id": source.source_asset_id,
                    "source_hosted_html_sha256": source.hosted_html_sha256,
                    "twin_source": {"kind": source_kind, "id": source_id},
                    "members": members,
                    "appendix_html_sha256": appendix_sha,
                    "object_locator": locator,
                })
                manifest_sha = _sha(manifest_json)
                identity = {
                    "source_asset_id": source.source_asset_id,
                    "source_document_id": f"twin-note-merge-bridge:{bridge_id}",
                    "source_sha256": manifest_sha,
                    "converter_id": BRIDGE_POLICY,
                    "converter_version": BRIDGE_VERSION,
                    "sanitizer_policy": BRIDGE_POLICY,
                    "sanitizer_version": BRIDGE_VERSION,
                }
                projection = HtmlProjectionContract(
                    **identity,
                    projection_id=derive_projection_id(**identity),
                    status="ready",
                    hosted_html_locator=locator,
                    hosted_html_sha256=appendix_sha,
                )
                con.execute(
                    "INSERT INTO twin_note_merge_bridges (bridge_id,owner_user_id,idempotency_key,"
                    "request_json,request_sha256,source_projection_id,twin_source_kind,twin_source_id,"
                    "manifest_json,manifest_sha256,appendix_html_bytes,appendix_html_byte_count,"
                    "appendix_html_sha256,projection_id,object_locator) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [bridge_id, owner_user_id, idempotency_key, request_json, request_sha,
                     source_projection_id, source_kind, source_id, manifest_json, manifest_sha,
                     appendix, len(appendix), appendix_sha, projection.projection_id, locator],
                )
                for member in members:
                    con.execute(
                        "INSERT INTO twin_note_merge_bridge_members VALUES (?,?,?,?,?,?,?)",
                        [bridge_id, *member.values()],
                    )
                store = ProjectionStore(con)
                existing = con.execute(
                    "SELECT projection_json FROM html_projections WHERE projection_id=?",
                    [projection.projection_id],
                ).fetchone()
                if existing is None:
                    con.execute(
                        "INSERT INTO html_projections VALUES (?,?,?)",
                        [projection.projection_id, _canonical(projection.identity()),
                         _canonical(projection.model_dump(mode="json"))],
                    )
                elif store.load(projection.projection_id) != projection:
                    raise MergeBridgeIntegrity
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return bridge_id

    def recover(self, *, bridge_id: str | None = None) -> list[str]:
        published: list[str] = []
        with connect_write(self.db_path, purpose="twin_note/merge_bridge_recover") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                where, args = (" WHERE bridge_id=?", [bridge_id]) if bridge_id else ("", [])
                rows = con.execute(
                    "SELECT bridge_id,object_locator,appendix_html_sha256,appendix_html_bytes,object_state "
                    "FROM twin_note_merge_bridges" + where + " ORDER BY created_at,bridge_id", args
                ).fetchall()
                for identity, locator, digest, blob, state in rows:
                    payload = bytes(blob)
                    if _sha(payload) != digest:
                        raise MergeBridgeIntegrity
                    self.publisher.publish_one("tmbe-" + _sha(str(identity))[:32], locator, digest, payload)
                    if state == "pending":
                        member_count = con.execute(
                            "SELECT count(*) FROM twin_note_merge_bridge_members WHERE bridge_id=?",
                            [identity],
                        ).fetchone()[0]
                        if not member_count:
                            raise MergeBridgeIntegrity
                        changed = con.execute(
                            "UPDATE twin_note_merge_bridges SET object_state='published',"
                            "publication_attempt_count=publication_attempt_count+1,published_at=CURRENT_TIMESTAMP "
                            "WHERE bridge_id=? AND object_state='pending' RETURNING bridge_id", [identity]
                        ).fetchone()
                        if changed:
                            published.append(str(identity))
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return published

    def reopen(
        self, *, owner_user_id: str, bridge_id: str, con: Any | None = None
    ) -> MergeBridgeResult:
        context = connect_read(self.db_path) if con is None else nullcontext(con)
        with context as con:
            row = con.execute(
                "SELECT source_projection_id,twin_source_kind,twin_source_id,request_json,request_sha256,"
                "manifest_json,manifest_sha256,appendix_html_bytes,appendix_html_sha256,projection_id,"
                "object_locator,object_state FROM twin_note_merge_bridges "
                "WHERE owner_user_id=? AND bridge_id=?", [owner_user_id, bridge_id]
            ).fetchone()
            if row is None:
                raise MergeBridgeUnavailable
            source_projection_id, kind, source_id, request_json, request_sha, manifest_json, manifest_sha, blob, html_sha, projection_id, locator, state = row
            if state != "published" or _sha(str(request_json)) != request_sha or _sha(str(manifest_json)) != manifest_sha or _sha(bytes(blob)) != html_sha:
                raise MergeBridgeIntegrity
            source = self._source_projection(con, owner_user_id, str(source_projection_id))
            revisions = self._source_revisions(con, owner_user_id, str(kind), str(source_id))
            members = con.execute(
                "SELECT member_ordinal,revision_id,note_ordinal,revision_body_sha256,"
                "revision_html_sha256,canonical_note_sha256 FROM twin_note_merge_bridge_members "
                "WHERE bridge_id=? ORDER BY member_ordinal", [bridge_id]
            ).fetchall()
            if not members or [item[0] for item in members] != list(range(len(members))):
                raise MergeBridgeIntegrity
            by_id = {revision.revision_id: revision for revision in revisions}
            rendered = []
            for _ordinal, revision_id, note_ordinal, body_sha, revision_html_sha, note_sha in members:
                revision = by_id.get(revision_id)
                if revision is None or (revision.body_sha256, revision.html_sha256) != (body_sha, revision_html_sha) or note_ordinal >= len(revision.body.agent_notes):
                    raise MergeBridgeIntegrity
                note, source_count = self._public_note(revision.body.agent_notes[note_ordinal])
                if _sha(note) != note_sha:
                    raise MergeBridgeIntegrity
                rendered.append((note, source_count))
            appendix = self._render(rendered)
            member_keys = ("member_ordinal", "revision_id", "note_ordinal",
                           "revision_body_sha256", "revision_html_sha256", "canonical_note_sha256")
            member_manifest = [dict(zip(member_keys, item, strict=True)) for item in members]
            expected_request = _canonical({
                "source_projection_id": source_projection_id,
                "source": {"kind": kind, "id": source_id},
                "selected_notes": [{"revision_id": item[1], "note_ordinal": item[2]}
                                   for item in members],
            })
            expected_manifest = {
                "bridge_policy": BRIDGE_POLICY,
                "bridge_version": BRIDGE_VERSION,
                "source_projection_id": source.projection_id,
                "source_asset_id": source.source_asset_id,
                "source_hosted_html_sha256": source.hosted_html_sha256,
                "twin_source": {"kind": kind, "id": source_id},
                "members": member_manifest,
                "appendix_html_sha256": html_sha,
                "object_locator": locator,
            }
            if (request_json != expected_request or _canonical(expected_manifest) != manifest_json
                    or appendix != bytes(blob)):
                raise MergeBridgeIntegrity
            stored = con.execute("SELECT projection_json FROM html_projections WHERE projection_id=?", [projection_id]).fetchone()
            try:
                projection = HtmlProjectionContract.model_validate_json(str(stored[0]) if stored else "")
            except (ValidationError, IndexError) as exc:
                raise MergeBridgeIntegrity from exc
            if (projection.status != "ready" or projection.source_sha256 != manifest_sha
                    or projection.hosted_html_locator != locator or projection.hosted_html_sha256 != html_sha
                    or projection.source_asset_id != source.source_asset_id
                    or projection.source_document_id != f"twin-note-merge-bridge:{bridge_id}"
                    or (projection.converter_id, projection.converter_version,
                        projection.sanitizer_policy, projection.sanitizer_version)
                    != (BRIDGE_POLICY, BRIDGE_VERSION, BRIDGE_POLICY, BRIDGE_VERSION)):
                raise MergeBridgeIntegrity
            try:
                MergeDraftRepository(
                    db_path=self.db_path, projection_root=self.publication_root
                )._load_member(projection)
            except MergeDraftError as exc:
                raise MergeBridgeIntegrity from exc
            return MergeBridgeResult(str(projection_id), str(source_projection_id), str(kind), str(source_id), len(members), str(html_sha))

    def _source_projection(self, con: Any, owner: str, projection_id: str) -> HtmlProjectionContract:
        row = con.execute("SELECT projection_json FROM html_projections WHERE projection_id=?", [projection_id]).fetchone()
        try:
            projection = HtmlProjectionContract.model_validate_json(str(row[0]) if row else "")
        except ValidationError as exc:
            raise MergeBridgeUnavailable from exc
        owned = con.execute("SELECT 1 FROM documents WHERE document_id=? AND owner_user_id=?", [projection.source_document_id, owner]).fetchone()
        if projection.status != "ready" or owned != (1,):
            raise MergeBridgeUnavailable
        try:
            MergeDraftRepository(
                db_path=self.db_path, projection_root=self.publication_root
            )._load_member(projection)
        except MergeDraftError as exc:
            raise MergeBridgeUnavailable from exc
        return projection

    def _source_revisions(self, con: Any, owner: str, kind: str, source_id: str) -> list[VerifiedRevision]:
        try:
            if kind == "revision":
                return [self.serving.revision_on(con, owner, source_id)]
            if kind == "composition":
                return self.serving.verified_composition_on(con, owner, source_id).members
        except (TwinNoteUnavailable, TwinNoteIntegrityError) as exc:
            raise MergeBridgeUnavailable from exc
        raise MergeBridgeUnavailable

    @staticmethod
    def _public_note(value: str) -> tuple[str, int]:
        prefix, separator, text = value.partition("] ")
        if not separator or not prefix.startswith("[") or not text:
            raise MergeBridgeIntegrity
        pieces = prefix[1:].split(" | ")
        if len(pieces) != 3 or not pieces[2]:
            raise MergeBridgeIntegrity
        return text, len(pieces[2].split(","))

    @staticmethod
    def _render(notes: Sequence[tuple[str, int]]) -> bytes:
        items = "".join(
            f'<li><p>Selection {index + 1}</p><p>{html.escape(text)}</p>'
            f'<p>Source attribution count: {count}</p></li>'
            for index, (text, count) in enumerate(notes)
        )
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<title>Twin-note appendix</title></head><body><main>'
            '<h1>Advisory machine-authored twin-note appendix</h1>'
            '<p>Selected notes are derived commentary and are not source authorship.</p>'
            f'<ol>{items}</ol></main></body></html>'
        ).encode()


__all__ = ["MergeBridgeConflict", "MergeBridgeIntegrity", "MergeBridgeResult",
           "MergeBridgeUnavailable", "SelectedNote", "TwinNoteMergeBridge"]
