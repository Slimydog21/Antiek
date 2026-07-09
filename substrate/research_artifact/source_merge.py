"""Reviewed source/twin merge apply ledger (SPR-AHT-08).

This module owns the first durable apply boundary after a Reader draft merge
review. It records a deterministic source/twin revision receipt under the
DuckDB write lock and emits a metadata-only audit event. It deliberately does
not rewrite the source book body yet; that later body writer must consume this
receipt rather than bypass it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.event_log import log_event

SOURCE_MERGE_APPLIED = "source_merge.applied"
SOURCE_MERGE_COMMITTED = "source_merge.committed"
SOURCE_MERGE_RESTORED = "source_merge.restored"


@dataclass(frozen=True)
class SourceMergeApplyReceipt:
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str | None
    member_investigation_ids: list[str]
    hash_conflicts_acknowledged: bool


@dataclass(frozen=True)
class SourceMergePreviewReceipt:
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    member_investigation_ids: list[str]
    before_source_hash: str
    after_source_hash: str
    before_twin_hash: str
    after_twin_hash: str
    source_bytes_before: int
    source_bytes_after: int
    twin_bytes_after: int
    writes_performed: bool


@dataclass(frozen=True)
class SourceMergeCommitReceipt:
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str | None
    member_investigation_ids: list[str]
    before_source_hash: str
    after_source_hash: str
    before_twin_hash: str
    after_twin_hash: str
    source_bytes_before: int
    source_bytes_after: int
    twin_bytes_after: int
    writes_performed: bool


@dataclass(frozen=True)
class SourceMergeRestoreReceipt:
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str | None
    before_source_hash: str
    restored_source_hash: str
    writes_performed: bool


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"source merge apply requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


def _ensure_schema(con: LockedConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS source_merge_revisions (
            apply_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            source_revision_id TEXT NOT NULL,
            twin_revision_id TEXT NOT NULL,
            parent_reading_thread_id TEXT NOT NULL,
            draft_merge_path TEXT NOT NULL,
            compose_index_path TEXT NOT NULL,
            member_investigation_ids_json TEXT NOT NULL,
            expected_content_hashes_json TEXT NOT NULL,
            hash_conflicts_json TEXT NOT NULL,
            hash_conflicts_acknowledged BOOLEAN NOT NULL,
            operator_reviewer TEXT,
            event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _ensure_commit_schema(con: LockedConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS source_merge_body_commits (
            commit_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            source_revision_id TEXT NOT NULL,
            twin_revision_id TEXT NOT NULL,
            parent_reading_thread_id TEXT NOT NULL,
            draft_merge_path TEXT NOT NULL,
            compose_index_path TEXT NOT NULL,
            member_investigation_ids_json TEXT NOT NULL,
            expected_content_hashes_json TEXT NOT NULL,
            twin_body_json TEXT NOT NULL,
            before_source_body TEXT NOT NULL,
            before_source_hash TEXT NOT NULL,
            after_source_hash TEXT NOT NULL,
            before_twin_hash TEXT NOT NULL,
            after_twin_hash TEXT NOT NULL,
            source_bytes_before INTEGER NOT NULL,
            source_bytes_after INTEGER NOT NULL,
            twin_bytes_after INTEGER NOT NULL,
            event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute("ALTER TABLE source_merge_body_commits ADD COLUMN IF NOT EXISTS before_source_body TEXT")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS source_merge_body_restores (
            restore_id TEXT PRIMARY KEY,
            commit_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source_revision_id TEXT NOT NULL,
            twin_revision_id TEXT NOT NULL,
            before_source_hash TEXT NOT NULL,
            restored_source_hash TEXT NOT NULL,
            parent_reading_thread_id TEXT NOT NULL,
            event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _canonical_apply_id(
    *,
    document_id: str,
    draft_merge_path: str,
    compose_index_path: str,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
) -> str:
    blob = json.dumps(
        {
            "document_id": document_id,
            "draft_merge_path": draft_merge_path,
            "compose_index_path": compose_index_path,
            "member_investigation_ids": member_investigation_ids,
            "expected_content_hashes": expected_content_hashes,
            "hash_conflicts": hash_conflicts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hash_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _read_reviewed_draft(draft_merge_path: str) -> str:
    path = Path(draft_merge_path)
    if not path.is_file():
        raise ValueError("source_merge_draft_merge_not_found")
    return path.read_text(encoding="utf-8")


def _preview_merge_payload(
    *,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
) -> str:
    return json.dumps(
        {
            "kind": "antiek.source_merge.preview_payload",
            "member_investigation_ids": member_investigation_ids,
            "expected_content_hashes": expected_content_hashes,
            "hash_conflicts": hash_conflicts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _source_after_text(before_source: str, *, draft_merge_path: str, draft_html: str) -> str:
    return "\n\n".join(
        part
        for part in [
            before_source.rstrip(),
            "<!-- antiek-source-merge-start -->",
            f"<!-- draft_merge_path: {draft_merge_path} -->",
            draft_html.strip(),
            "<!-- antiek-source-merge-end -->",
        ]
        if part
    )


def _source_merge_preview(
    con: LockedConnection,
    *,
    document_id: str,
    draft_merge_path: str,
    compose_index_path: str,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
) -> SourceMergePreviewReceipt:
    member_ids = [iid.strip() for iid in member_investigation_ids if iid.strip()]
    apply_id = _canonical_apply_id(
        document_id=document_id,
        draft_merge_path=draft_merge_path,
        compose_index_path=compose_index_path,
        member_investigation_ids=member_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )
    suffix = apply_id[:16]
    source_revision_id = f"srcmerge-{document_id}-{suffix}"
    twin_revision_id = f"twinmerge-{document_id}-{suffix}"

    row = con.execute(
        "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        raise ValueError("source_merge_source_document_not_found")

    before_source = row[0] or ""
    draft_html = _read_reviewed_draft(draft_merge_path)
    after_source = _source_after_text(
        before_source,
        draft_merge_path=draft_merge_path,
        draft_html=draft_html,
    )
    twin_payload = _preview_merge_payload(
        member_investigation_ids=member_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )
    return SourceMergePreviewReceipt(
        status="previewed",
        document_id=document_id,
        source_revision_id=source_revision_id,
        twin_revision_id=twin_revision_id,
        member_investigation_ids=member_ids,
        before_source_hash=_hash_text(before_source),
        after_source_hash=_hash_text(after_source),
        before_twin_hash=_hash_text(None),
        after_twin_hash=_hash_text(twin_payload),
        source_bytes_before=len(before_source.encode("utf-8")),
        source_bytes_after=len(after_source.encode("utf-8")),
        twin_bytes_after=len(twin_payload.encode("utf-8")),
        writes_performed=False,
    )


def preview_source_merge_review(
    con: LockedConnection,
    *,
    document_id: str,
    draft_merge_path: str,
    compose_index_path: str,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
) -> SourceMergePreviewReceipt:
    """Compute source/twin revision evidence without mutating storage."""

    _require_locked(con)
    return _source_merge_preview(
        con,
        document_id=document_id,
        draft_merge_path=draft_merge_path,
        compose_index_path=compose_index_path,
        member_investigation_ids=member_investigation_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )


def commit_source_merge_review(
    con: LockedConnection,
    *,
    document_id: str,
    parent_reading_thread_id: str,
    draft_merge_path: str,
    compose_index_path: str,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
    expected_source_revision_id: str,
    expected_twin_revision_id: str,
    expected_before_source_hash: str,
    expected_after_source_hash: str,
    expected_before_twin_hash: str,
    expected_after_twin_hash: str,
    operator_reviewer: str | None = None,
    events_dir: str | None = None,
) -> SourceMergeCommitReceipt:
    """Rewrite the source body from a bound reviewed preview."""

    _require_locked(con)
    _ensure_commit_schema(con)
    member_ids = [iid.strip() for iid in member_investigation_ids if iid.strip()]
    commit_id = _canonical_apply_id(
        document_id=document_id,
        draft_merge_path=draft_merge_path,
        compose_index_path=compose_index_path,
        member_investigation_ids=member_ids,
        expected_content_hashes={**expected_content_hashes, "__after_source_hash": expected_after_source_hash},
        hash_conflicts=hash_conflicts,
    )
    existing = con.execute(
        """
        SELECT source_revision_id, twin_revision_id, event_id,
               member_investigation_ids_json, before_source_hash,
               after_source_hash, before_twin_hash, after_twin_hash,
               source_bytes_before, source_bytes_after, twin_bytes_after
        FROM source_merge_body_commits
        WHERE commit_id = ?
        """,
        [commit_id],
    ).fetchone()
    if existing:
        return SourceMergeCommitReceipt(
            status="committed",
            document_id=document_id,
            source_revision_id=existing[0],
            twin_revision_id=existing[1],
            event_id=existing[2],
            member_investigation_ids=json.loads(existing[3]),
            before_source_hash=existing[4],
            after_source_hash=existing[5],
            before_twin_hash=existing[6],
            after_twin_hash=existing[7],
            source_bytes_before=int(existing[8]),
            source_bytes_after=int(existing[9]),
            twin_bytes_after=int(existing[10]),
            writes_performed=False,
        )

    preview = _source_merge_preview(
        con,
        document_id=document_id,
        draft_merge_path=draft_merge_path,
        compose_index_path=compose_index_path,
        member_investigation_ids=member_investigation_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )
    expected = {
        "source_revision_id": expected_source_revision_id,
        "twin_revision_id": expected_twin_revision_id,
        "before_source_hash": expected_before_source_hash,
        "after_source_hash": expected_after_source_hash,
        "before_twin_hash": expected_before_twin_hash,
        "after_twin_hash": expected_after_twin_hash,
    }
    actual = {
        "source_revision_id": preview.source_revision_id,
        "twin_revision_id": preview.twin_revision_id,
        "before_source_hash": preview.before_source_hash,
        "after_source_hash": preview.after_source_hash,
        "before_twin_hash": preview.before_twin_hash,
        "after_twin_hash": preview.after_twin_hash,
    }
    if actual != expected:
        raise ValueError("source_merge_preview_binding_mismatch")

    draft_html = _read_reviewed_draft(draft_merge_path)
    current = con.execute(
        "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    before_source = current[0] or ""
    after_source = _source_after_text(
        before_source,
        draft_merge_path=draft_merge_path,
        draft_html=draft_html,
    )
    con.execute(
        "UPDATE documents SET raw_text = ? WHERE document_id = ?",
        [after_source, document_id],
    )
    payload = {
        "document_id": document_id,
        "source_revision_id": preview.source_revision_id,
        "twin_revision_id": preview.twin_revision_id,
        "draft_merge_path": draft_merge_path,
        "compose_index_path": compose_index_path,
        "member_investigation_ids": preview.member_investigation_ids,
        "expected_content_hashes": expected_content_hashes,
        "before_source_hash": preview.before_source_hash,
        "after_source_hash": preview.after_source_hash,
        "before_twin_hash": preview.before_twin_hash,
        "after_twin_hash": preview.after_twin_hash,
        "source_bytes_before": preview.source_bytes_before,
        "source_bytes_after": preview.source_bytes_after,
        "twin_bytes_after": preview.twin_bytes_after,
        "operator_reviewer": operator_reviewer,
        "source_book_body_rewritten": True,
        "twin_document_body_rewritten": True,
    }
    event_id = log_event(
        parent_reading_thread_id,
        SOURCE_MERGE_COMMITTED,
        payload=payload,
        role="read/source_merge_commit",
        policy_id="read/source_merge/commit",
        document_id=document_id,
        events_dir=events_dir,
    )
    twin_body_json = _preview_merge_payload(
        member_investigation_ids=preview.member_investigation_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )
    con.execute(
        """
        INSERT INTO source_merge_body_commits (
            commit_id, document_id, source_revision_id, twin_revision_id,
            parent_reading_thread_id, draft_merge_path, compose_index_path,
            member_investigation_ids_json, expected_content_hashes_json,
            twin_body_json, before_source_body,
            before_source_hash, after_source_hash, before_twin_hash,
            after_twin_hash, source_bytes_before, source_bytes_after,
            twin_bytes_after, event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            commit_id,
            document_id,
            preview.source_revision_id,
            preview.twin_revision_id,
            parent_reading_thread_id,
            draft_merge_path,
            compose_index_path,
            json.dumps(preview.member_investigation_ids, sort_keys=True),
            json.dumps(expected_content_hashes, sort_keys=True),
            twin_body_json,
            before_source,
            preview.before_source_hash,
            preview.after_source_hash,
            preview.before_twin_hash,
            preview.after_twin_hash,
            preview.source_bytes_before,
            preview.source_bytes_after,
            preview.twin_bytes_after,
            event_id,
        ],
    )
    return SourceMergeCommitReceipt(
        status="committed",
        document_id=document_id,
        source_revision_id=preview.source_revision_id,
        twin_revision_id=preview.twin_revision_id,
        event_id=event_id,
        member_investigation_ids=preview.member_investigation_ids,
        before_source_hash=preview.before_source_hash,
        after_source_hash=preview.after_source_hash,
        before_twin_hash=preview.before_twin_hash,
        after_twin_hash=preview.after_twin_hash,
        source_bytes_before=preview.source_bytes_before,
        source_bytes_after=preview.source_bytes_after,
        twin_bytes_after=preview.twin_bytes_after,
        writes_performed=True,
    )


def restore_source_merge_review(
    con: LockedConnection,
    *,
    document_id: str,
    parent_reading_thread_id: str,
    source_revision_id: str,
    twin_revision_id: str,
    expected_after_source_hash: str,
    expected_before_source_hash: str,
    operator_reviewer: str | None = None,
    events_dir: str | None = None,
) -> SourceMergeRestoreReceipt:
    """Restore source body from the body snapshot captured at commit time."""

    _require_locked(con)
    _ensure_commit_schema(con)
    row = con.execute(
        """
        SELECT commit_id, before_source_body, before_source_hash, after_source_hash
        FROM source_merge_body_commits
        WHERE document_id = ?
          AND source_revision_id = ?
          AND twin_revision_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [document_id, source_revision_id, twin_revision_id],
    ).fetchone()
    if row is None:
        raise ValueError("source_merge_commit_not_found")
    commit_id, before_source_body, before_source_hash, after_source_hash = row
    if not before_source_body and before_source_hash != _hash_text(""):
        raise ValueError("source_merge_restore_body_unavailable")
    if before_source_hash != expected_before_source_hash or after_source_hash != expected_after_source_hash:
        raise ValueError("source_merge_restore_binding_mismatch")

    restore_id = hashlib.sha256(
        json.dumps(
            {
                "commit_id": commit_id,
                "document_id": document_id,
                "source_revision_id": source_revision_id,
                "twin_revision_id": twin_revision_id,
                "expected_after_source_hash": expected_after_source_hash,
                "expected_before_source_hash": expected_before_source_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = con.execute(
        """
        SELECT event_id, restored_source_hash
        FROM source_merge_body_restores
        WHERE restore_id = ?
        """,
        [restore_id],
    ).fetchone()
    if existing:
        return SourceMergeRestoreReceipt(
            status="restored",
            document_id=document_id,
            source_revision_id=source_revision_id,
            twin_revision_id=twin_revision_id,
            event_id=existing[0],
            before_source_hash=before_source_hash,
            restored_source_hash=existing[1],
            writes_performed=False,
        )

    current = con.execute(
        "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if current is None:
        raise ValueError("source_merge_source_document_not_found")
    current_hash = _hash_text(current[0] or "")
    if current_hash != after_source_hash:
        raise ValueError("source_merge_restore_current_hash_mismatch")

    con.execute(
        "UPDATE documents SET raw_text = ? WHERE document_id = ?",
        [before_source_body or "", document_id],
    )
    restored_hash = _hash_text(before_source_body or "")
    payload = {
        "document_id": document_id,
        "source_revision_id": source_revision_id,
        "twin_revision_id": twin_revision_id,
        "before_source_hash": before_source_hash,
        "after_source_hash": after_source_hash,
        "restored_source_hash": restored_hash,
        "operator_reviewer": operator_reviewer,
        "source_book_body_restored": True,
    }
    event_id = log_event(
        parent_reading_thread_id,
        SOURCE_MERGE_RESTORED,
        payload=payload,
        role="read/source_merge_restore",
        policy_id="read/source_merge/restore",
        document_id=document_id,
        events_dir=events_dir,
    )
    con.execute(
        """
        INSERT INTO source_merge_body_restores (
            restore_id, commit_id, document_id, source_revision_id,
            twin_revision_id, before_source_hash, restored_source_hash,
            parent_reading_thread_id, event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            restore_id,
            commit_id,
            document_id,
            source_revision_id,
            twin_revision_id,
            before_source_hash,
            restored_hash,
            parent_reading_thread_id,
            event_id,
        ],
    )
    return SourceMergeRestoreReceipt(
        status="restored",
        document_id=document_id,
        source_revision_id=source_revision_id,
        twin_revision_id=twin_revision_id,
        event_id=event_id,
        before_source_hash=before_source_hash,
        restored_source_hash=restored_hash,
        writes_performed=True,
    )


def apply_source_merge_review(
    con: LockedConnection,
    *,
    document_id: str,
    parent_reading_thread_id: str,
    draft_merge_path: str,
    compose_index_path: str,
    member_investigation_ids: list[str],
    expected_content_hashes: dict[str, str],
    hash_conflicts: list[list[str]],
    hash_conflicts_acknowledged: bool,
    operator_reviewer: str | None = None,
    events_dir: str | None = None,
) -> SourceMergeApplyReceipt:
    """Record one reviewed apply receipt under the DuckDB write lock.

    Idempotency is keyed on the reviewed draft path, compose index, member ids,
    expected hashes, conflicts, and document id. Re-submitting the same reviewed
    packet returns the original receipt rather than emitting another event.
    """

    _require_locked(con)
    _ensure_schema(con)
    member_ids = [iid.strip() for iid in member_investigation_ids if iid.strip()]
    apply_id = _canonical_apply_id(
        document_id=document_id,
        draft_merge_path=draft_merge_path,
        compose_index_path=compose_index_path,
        member_investigation_ids=member_ids,
        expected_content_hashes=expected_content_hashes,
        hash_conflicts=hash_conflicts,
    )
    suffix = apply_id[:16]
    source_revision_id = f"srcmerge-{document_id}-{suffix}"
    twin_revision_id = f"twinmerge-{document_id}-{suffix}"

    existing = con.execute(
        """
        SELECT source_revision_id, twin_revision_id, event_id,
               member_investigation_ids_json, hash_conflicts_acknowledged
        FROM source_merge_revisions
        WHERE apply_id = ?
        """,
        [apply_id],
    ).fetchone()
    if existing:
        return SourceMergeApplyReceipt(
            status="applied",
            document_id=document_id,
            source_revision_id=existing[0],
            twin_revision_id=existing[1],
            event_id=existing[2],
            member_investigation_ids=json.loads(existing[3]),
            hash_conflicts_acknowledged=bool(existing[4]),
        )

    payload = {
        "document_id": document_id,
        "source_revision_id": source_revision_id,
        "twin_revision_id": twin_revision_id,
        "draft_merge_path": draft_merge_path,
        "compose_index_path": compose_index_path,
        "member_investigation_ids": member_ids,
        "expected_content_hashes": expected_content_hashes,
        "hash_conflict_count": len(hash_conflicts),
        "hash_conflicts": hash_conflicts,
        "hash_conflicts_acknowledged": hash_conflicts_acknowledged,
        "operator_reviewer": operator_reviewer,
        "source_book_body_rewritten": False,
        "twin_document_body_rewritten": False,
    }
    event_id = log_event(
        parent_reading_thread_id,
        SOURCE_MERGE_APPLIED,
        payload=payload,
        role="read/source_merge_apply",
        policy_id="read/source_merge/apply",
        document_id=document_id,
        events_dir=events_dir,
    )
    con.execute(
        """
        INSERT INTO source_merge_revisions (
            apply_id, document_id, source_revision_id, twin_revision_id,
            parent_reading_thread_id, draft_merge_path, compose_index_path,
            member_investigation_ids_json, expected_content_hashes_json,
            hash_conflicts_json, hash_conflicts_acknowledged, operator_reviewer,
            event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            apply_id,
            document_id,
            source_revision_id,
            twin_revision_id,
            parent_reading_thread_id,
            draft_merge_path,
            compose_index_path,
            json.dumps(member_ids, sort_keys=True),
            json.dumps(expected_content_hashes, sort_keys=True),
            json.dumps(hash_conflicts, sort_keys=True),
            hash_conflicts_acknowledged,
            operator_reviewer,
            event_id,
        ],
    )
    return SourceMergeApplyReceipt(
        status="applied",
        document_id=document_id,
        source_revision_id=source_revision_id,
        twin_revision_id=twin_revision_id,
        event_id=event_id,
        member_investigation_ids=member_ids,
        hash_conflicts_acknowledged=hash_conflicts_acknowledged,
    )
