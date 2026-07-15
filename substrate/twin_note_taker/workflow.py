"""Owner-bound preview/apply workflow for immutable V20 -> V21 twin notes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from runtime.db_lock import connect_read

from .compression import (COMPRESSOR_VERSION, MAX_MEMBERS, MAX_NOTES, MAX_SOURCE_EVENTS,
                          RENDERER_VERSION, DurableTwinNoteCompression,
                          OwnershipResolver, TwinNoteCompressionError, _canonical,
                          build_window_admission)
from .serving import TwinNoteIntegrityError, TwinNoteServingService, TwinNoteUnavailable


class TwinNoteWorkflowUnavailable(LookupError): pass
class TwinNoteWorkflowIntegrity(RuntimeError): pass
class TwinNoteWorkflowConflict(RuntimeError): pass
class TwinNoteWorkflowInput(ValueError): pass


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Admission:
    account_id: str
    asset_id: str
    window_ids: tuple[str, ...]
    expected_predecessor: str | None
    preview_digest: str
    members: list[dict[str, Any]]
    note_count: int
    source_count: int

    def response(self) -> dict[str, Any]:
        return {"asset_id": self.asset_id, "expected_predecessor": self.expected_predecessor,
                "preview_digest": self.preview_digest, "members": self.members,
                "note_count": self.note_count, "source_count": self.source_count}


class TwinNoteWorkflow:
    def __init__(self, ownership_resolver: OwnershipResolver, *, db_path: str,
                 publication_root: str, events_dir: str | None = None) -> None:
        self.db_path = db_path
        self.resolver = ownership_resolver
        self.compressor = DurableTwinNoteCompression(ownership_resolver, db_path=db_path,
            publication_root=publication_root, events_dir=events_dir)

    def _admit(self, account_id: str, asset_id: str, window_ids: Sequence[str]) -> Admission:
        try:
            admitted = build_window_admission(db_path=self.db_path,ownership_resolver=self.resolver,
                account_id=account_id,asset_id=asset_id,window_ids=window_ids)
        except TwinNoteCompressionError as exc:
            if "missing" in str(exc) or "ownership resolver" in str(exc):
                raise TwinNoteWorkflowUnavailable from exc
            if "window_ids" in str(exc) or "duplicate" in str(exc) or "canonical non-empty" in str(exc):
                raise TwinNoteWorkflowInput(str(exc)) from exc
            raise TwinNoteWorkflowIntegrity from exc
        with connect_read(self.db_path) as con:
            current = con.execute("SELECT r.revision_id FROM twin_note_revisions r WHERE r.account_id=? AND r.asset_id=? "
                "AND NOT EXISTS (SELECT 1 FROM twin_note_revisions s WHERE s.account_id=r.account_id AND "
                "s.asset_id=r.asset_id AND s.supersedes_revision_id=r.revision_id)",
                [admitted.account_id,admitted.asset_id]).fetchall()
        if len(current) > 1: raise TwinNoteWorkflowIntegrity
        predecessor = current[0][0] if current else None
        members = admitted.members()
        digest = _sha(_canonical({"account_id":admitted.account_id,"asset_id":admitted.asset_id,
            "expected_predecessor":predecessor,"compressor_version":COMPRESSOR_VERSION,
            "renderer_version":RENDERER_VERSION,"members":members}))
        return Admission(admitted.account_id,admitted.asset_id,admitted.window_ids,predecessor,digest,
                         members,len(admitted.attributed_json),len(admitted.source_event_ids))

    def preview(self, *, account_id: str, asset_id: str, window_ids: Sequence[str]) -> Admission:
        return self._admit(account_id, asset_id, window_ids)

    def apply(self, *, account_id: str, asset_id: str, window_ids: Sequence[str],
              expected_predecessor: str | None, preview_digest: str,
              idempotency_key: str) -> dict[str, Any]:
        if type(idempotency_key) is not str or not 16 <= len(idempotency_key) <= 128:
            raise TwinNoteWorkflowInput("invalid idempotency_key")
        request_sha = _sha(_canonical({"asset_id":asset_id,"window_ids":list(window_ids),
            "expected_predecessor":expected_predecessor,"preview_digest":preview_digest,
            "idempotency_key":idempotency_key}))
        with connect_read(self.db_path) as con:
            receipt = con.execute("SELECT request_sha256,preview_sha256,asset_id,expected_predecessor,revision_id,created_at FROM twin_note_revision_commands "
                "WHERE account_id=? AND idempotency_key=?", [account_id,idempotency_key]).fetchone()
        if receipt:
            expected=(request_sha,preview_digest,asset_id,expected_predecessor)
            if receipt[:4] != expected: raise TwinNoteWorkflowConflict("idempotency key reuse conflicts")
            try:
                verified=TwinNoteServingService(db_path=self.db_path).revision(account_id,receipt[4])
            except (TwinNoteUnavailable,TwinNoteIntegrityError) as exc: raise TwinNoteWorkflowIntegrity from exc
            if verified.asset_id != asset_id or verified.supersedes_revision_id != expected_predecessor:
                raise TwinNoteWorkflowIntegrity
            expected_created = (datetime(2000,1,1,tzinfo=UTC)
                + timedelta(seconds=int(_sha(verified.revision_id)[:8],16))).replace(tzinfo=None)
            if receipt[5] != expected_created:
                raise TwinNoteWorkflowIntegrity
            try:
                self.compressor.verify_replay_ledgers(verified)
            except TwinNoteCompressionError as exc:
                raise TwinNoteWorkflowIntegrity from exc
            self.compressor.recover(revision_id=verified.revision_id)
            return {"revision_id":verified.revision_id,"asset_id":verified.asset_id,
                    "supersedes_revision_id":verified.supersedes_revision_id,
                    "note_count":verified.note_count,"source_count":verified.source_count,"replayed":True,
                    "url":f"/research/twin-notes/revisions/{verified.revision_id}"}
        admission = self._admit(account_id,asset_id,window_ids)
        if admission.expected_predecessor != expected_predecessor or admission.preview_digest != preview_digest:
            raise TwinNoteWorkflowConflict("preview or predecessor is stale")
        try:
            revision = self.compressor.compress(account_id=account_id,asset_id=asset_id,
                window_ids=window_ids,expected_predecessor=expected_predecessor,
                command_receipt=(idempotency_key,request_sha,preview_digest))
        except TwinNoteCompressionError as exc: raise TwinNoteWorkflowConflict(str(exc)) from exc
        return {"revision_id":revision.revision_id,"asset_id":asset_id,
                "supersedes_revision_id":expected_predecessor,"note_count":revision.note_count,
                "source_count":revision.source_event_count,"replayed":False,
                "url":f"/research/twin-notes/revisions/{revision.revision_id}"}
