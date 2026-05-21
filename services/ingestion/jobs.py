"""Ingestion job log (M7).

The HTTP API returns a ``job_id`` for any URL that requires fetching;
the client polls /api/library/ingest/{job_id} until terminal. This
module is the storage layer for those jobs.

State machine:

  pending     → queued
  running     → fetch/extract/pipeline in progress
  succeeded   → document_id is set; error is null
  failed      → error is set with a short reason; error_detail
                optional longer trace

All writes go through ``runtime/db_lock.connect_write`` — single
writer discipline.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


JobStatus = str  # "pending" | "running" | "succeeded" | "failed"


@dataclass(frozen=True)
class IngestionJob:
    """One row in ``ingestion_jobs``."""

    job_id: str
    url: str
    user_id: str
    investigation_id: str
    status: JobStatus
    content_type: Optional[str] = None
    document_id: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None
    attempts: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


def _new_job_id() -> str:
    """Compact job id. ``job-<8-hex>`` — short enough for log lines,
    long enough that birthday collisions are negligible at our scale
    (we'd need ~10^9 jobs for a 1% collision probability)."""
    return "job-" + uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_schema(db_path: str) -> None:
    """Idempotent migration apply. Called by every writer before its
    first INSERT/UPDATE in the process."""
    from services.ingestion.migrations import apply_all
    apply_all(db_path)


def create_job(
    *,
    url: str,
    user_id: str,
    investigation_id: str = "__operator__",
    content_type: Optional[str] = None,
    metadata: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> IngestionJob:
    """Insert a fresh job in ``pending`` state. Returns the IngestionJob."""
    from runtime.db_lock import connect_write
    from substrate.graph import default_db_path

    resolved_db_path = db_path or default_db_path()
    _ensure_schema(resolved_db_path)

    job_id = _new_job_id()
    now = _now()
    md_json = json.dumps(metadata or {})
    with connect_write(resolved_db_path, purpose="ingestion/jobs/create") as con:
        con.execute(
            "INSERT INTO ingestion_jobs "
            "(job_id, url, user_id, investigation_id, status, content_type, "
            " attempts, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?)",
            [job_id, url, user_id, investigation_id, content_type, now, now, md_json],
        )
    return IngestionJob(
        job_id=job_id, url=url, user_id=user_id,
        investigation_id=investigation_id,
        status="pending", content_type=content_type,
        attempts=0, created_at=now, updated_at=now,
        metadata=metadata or {},
    )


def update_status(
    job_id: str,
    *,
    status: JobStatus,
    document_id: Optional[str] = None,
    content_type: Optional[str] = None,
    error: Optional[str] = None,
    error_detail: Optional[str] = None,
    bump_attempts: bool = False,
    metadata_patch: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> None:
    """Update a job's status. Multi-column UPDATE so the row stays
    consistent. ``metadata_patch`` is shallow-merged into existing
    metadata."""
    from runtime.db_lock import connect_write
    from substrate.graph import default_db_path
    resolved_db_path = db_path or default_db_path()
    _ensure_schema(resolved_db_path)
    now = _now()

    with connect_write(resolved_db_path, purpose="ingestion/jobs/update") as con:
        # Pull current row to merge metadata.
        cur = con.execute(
            "SELECT metadata FROM ingestion_jobs WHERE job_id = ?",
            [job_id],
        ).fetchone()
        if cur is None:
            raise ValueError(f"job_id not found: {job_id!r}")
        try:
            existing = json.loads(cur[0]) if cur[0] else {}
        except (json.JSONDecodeError, TypeError):
            existing = {}
        if metadata_patch:
            existing.update(metadata_patch)
        md_json = json.dumps(existing)

        sets = ["status = ?", "updated_at = ?", "metadata = ?"]
        params: list[object] = [status, now, md_json]
        if document_id is not None:
            sets.append("document_id = ?")
            params.append(document_id)
        if content_type is not None:
            sets.append("content_type = ?")
            params.append(content_type)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if error_detail is not None:
            sets.append("error_detail = ?")
            params.append(error_detail)
        if bump_attempts:
            sets.append("attempts = attempts + 1")
        params.append(job_id)
        con.execute(
            f"UPDATE ingestion_jobs SET {', '.join(sets)} WHERE job_id = ?",
            params,
        )


def get_job(
    job_id: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[IngestionJob]:
    """Read one job by id. Returns None if it doesn't exist."""
    import duckdb
    from substrate.graph import default_db_path
    resolved_db_path = db_path or default_db_path()
    if not os.path.exists(resolved_db_path):
        return None
    try:
        con = duckdb.connect(resolved_db_path, read_only=True)
    except Exception:  # noqa: BLE001
        return None
    try:
        row = con.execute(
            "SELECT job_id, url, user_id, investigation_id, status, "
            "       content_type, document_id, error, error_detail, "
            "       attempts, created_at, updated_at, metadata "
            "FROM ingestion_jobs WHERE job_id = ?",
            [job_id],
        ).fetchone()
    except Exception:  # noqa: BLE001 — table may not exist yet
        return None
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
    if row is None:
        return None
    metadata = {}
    if row[12]:
        try:
            metadata = json.loads(row[12])
        except (json.JSONDecodeError, TypeError):
            metadata = {}
    return IngestionJob(
        job_id=row[0], url=row[1], user_id=row[2],
        investigation_id=row[3], status=row[4],
        content_type=row[5], document_id=row[6],
        error=row[7], error_detail=row[8],
        attempts=row[9], created_at=row[10], updated_at=row[11],
        metadata=metadata,
    )
