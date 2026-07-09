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
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.event_log import log_event

SOURCE_MERGE_APPLIED = "source_merge.applied"


@dataclass(frozen=True)
class SourceMergeApplyReceipt:
    status: str
    document_id: str
    source_revision_id: str
    twin_revision_id: str
    event_id: str | None
    member_investigation_ids: list[str]
    hash_conflicts_acknowledged: bool


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
