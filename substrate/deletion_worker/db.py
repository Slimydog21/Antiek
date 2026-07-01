"""DuckDB persistence adapter for the deletion worker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from substrate.telemetry_preferences import (
    PreferenceStore,
    SqlitePreferenceStore,
    default_preference_store,
    delete_preferences_for_user,
)

from .worker import (
    CASCADE_TARGETS,
    DeletionRequest,
    DeletionRequestStatus,
    DeletionResult,
    DeletionResultKind,
    process_request,
)


def _normalize_status(value: str) -> DeletionRequestStatus:
    try:
        return DeletionRequestStatus(value)
    except ValueError:
        return DeletionRequestStatus.FAILED


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _table_exists(con, table: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = ?
        LIMIT 1
        """,
        [table],
    ).fetchone()
    return row is not None


def _delete(con, table: str, where: str, params: list[Any]) -> int:
    if not _table_exists(con, table):
        return 0
    count = int(
        con.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0],
    )
    con.execute(f"DELETE FROM {table} WHERE {where}", params)
    return count


def _delete_owned_deliverable_sections(con, user_id: str) -> int:
    if not _table_exists(con, "deliverable_sections"):
        return 0
    deleted = 0
    while True:
        rows = con.execute(
            """
            SELECT s.section_id
            FROM deliverable_sections s
            JOIN deliverables d ON d.deliverable_id = s.deliverable_id
            WHERE d.owner_user_id = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM deliverable_sections child
                  WHERE child.parent_section_id = s.section_id
              )
            """,
            [user_id],
        ).fetchall()
        if not rows:
            break
        section_ids = [str(row[0]) for row in rows]
        placeholders = ", ".join("?" for _ in section_ids)
        con.execute(
            f"DELETE FROM deliverable_sections WHERE section_id IN ({placeholders})",
            section_ids,
        )
        deleted += len(section_ids)
    return deleted


def load_requests_for_cycle(con) -> list[DeletionRequest]:
    """Load rows the worker is allowed to process this cycle."""
    rows = con.execute(
        """
        SELECT request_id, user_id, status, requested_at, updated_at, reason
        FROM deletion_requests
        WHERE status IN ('pending', 'confirmed')
        ORDER BY requested_at ASC
        """
    ).fetchall()
    return [
        DeletionRequest(
            request_id=str(row[0]),
            user_id=str(row[1]),
            status=_normalize_status(str(row[2])),
            requested_at=_as_datetime(row[3]),
            updated_at=_as_datetime(row[4]),
            reason=str(row[5]) if row[5] is not None else None,
        )
        for row in rows
    ]


def cascade_delete_user(
    con,
    user_id: str,
    *,
    preference_store: PreferenceStore,
) -> dict[str, int]:
    """Delete user-owned rows in dependency order.

    Ownership is direct (`owner_user_id`) or derived through owned parent rows.
    Tables without a proven ownership path are reported as zero rather than
    guessed against.
    """
    counts: dict[str, int] = {target: 0 for target in CASCADE_TARGETS}
    owned_docs = "SELECT document_id FROM documents WHERE owner_user_id = ?"
    owned_chunks = f"SELECT chunk_id FROM chunks WHERE document_id IN ({owned_docs})"

    counts["edges"] = _delete(
        con,
        "edges",
        f"chunk_id IN ({owned_chunks}) OR source_document_id IN ({owned_docs})",
        [user_id, user_id],
    )
    counts["chunk_tier_overrides"] = _delete(
        con,
        "chunk_tier_overrides",
        f"chunk_id IN ({owned_chunks})",
        [user_id],
    )
    counts["url_alias"] = _delete(
        con,
        "url_alias",
        f"document_id IN ({owned_docs})",
        [user_id],
    )
    counts["book_assets"] = _delete(
        con,
        "book_assets",
        f"document_id IN ({owned_docs})",
        [user_id],
    )

    counts["notebook_blocks"] = _delete(
        con,
        "notebook_blocks",
        "notebook_id IN (SELECT notebook_id FROM notebooks WHERE owner_user_id = ?)",
        [user_id],
    )
    counts["notebooks"] = _delete(con, "notebooks", "owner_user_id = ?", [user_id])
    counts["section_blocks"] = _delete(
        con,
        "section_blocks",
        """
        section_id IN (
            SELECT s.section_id
            FROM deliverable_sections s
            JOIN deliverables d ON d.deliverable_id = s.deliverable_id
            WHERE d.owner_user_id = ?
        )
        """,
        [user_id],
    )
    counts["outline_blocks"] = _delete(
        con,
        "outline_blocks",
        """
        section_id IN (
            SELECT s.section_id
            FROM deliverable_sections s
            JOIN deliverables d ON d.deliverable_id = s.deliverable_id
            WHERE d.owner_user_id = ?
        )
        """,
        [user_id],
    )
    counts["interviews"] = _delete(
        con,
        "interviews",
        f"""
        project_id IN (
            SELECT project_id FROM interview_projects WHERE owner_user_id = ?
        )
        OR transcript_document_id IN ({owned_docs})
        """,
        [user_id, user_id],
    )
    counts["interview_projects"] = _delete(
        con,
        "interview_projects",
        "owner_user_id = ?",
        [user_id],
    )
    counts["deliverable_sections"] = _delete_owned_deliverable_sections(con, user_id)
    counts["deliverables"] = _delete(
        con,
        "deliverables",
        "owner_user_id = ?",
        [user_id],
    )
    counts["chunks"] = _delete(
        con,
        "chunks",
        "document_id IN (SELECT document_id FROM documents WHERE owner_user_id = ?)",
        [user_id],
    )
    counts["documents"] = _delete(con, "documents", "owner_user_id = ?", [user_id])
    counts["user_telemetry_preferences"] = delete_preferences_for_user(
        preference_store,
        user_id=user_id,
    )
    return counts


def persist_cycle_results(con, results: list[DeletionResult]) -> None:
    """Persist worker outcomes to `deletion_requests`."""
    for result in results:
        if result.kind == DeletionResultKind.COMPLETED:
            con.execute(
                """
                UPDATE deletion_requests
                SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ? AND status IN ('pending', 'confirmed')
                """,
                [result.request_id],
            )
        elif result.kind == DeletionResultKind.FAILED:
            con.execute(
                """
                UPDATE deletion_requests
                SET status = 'failed', updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ? AND status IN ('pending', 'confirmed')
                """,
                [result.request_id],
            )


def run_db_cycle(
    con,
    *,
    now: datetime | None = None,
    preference_store: PreferenceStore | None = None,
) -> list[DeletionResult]:
    """Load processable deletion requests, cascade them, and persist statuses."""
    requests = load_requests_for_cycle(con)

    def _cascade(user_id: str) -> dict[str, int]:
        if preference_store is None:
            raise RuntimeError(
                "deletion worker requires a telemetry preference store; "
                "use run_db_cycle_at_path(...) or pass preference_store=..."
            )
        return cascade_delete_user(
            con,
            user_id,
            preference_store=preference_store,
        )

    results = [
        process_request(
            request,
            cascade=_cascade,
            now=now,
        )
        for request in requests
    ]
    persist_cycle_results(con, results)
    return results


def default_preference_store_for_graph_db(db_path: str | Path) -> SqlitePreferenceStore:
    """Return the telemetry-preference store for one graph DB path."""
    return default_preference_store(db_path)


def run_db_cycle_at_path(
    db_path: str | Path,
    *,
    now: datetime | None = None,
    preference_store: PreferenceStore | None = None,
) -> list[DeletionResult]:
    """Run one deletion-worker cycle for a graph DB path.

    When no preference store is injected, this uses the shared telemetry
    preference resolver: `ANTIEK_TELEMETRY_PREFERENCES_PATH` first, otherwise
    `telemetry_preferences.sqlite` beside `db_path`.
    """
    from runtime.db_lock import connect_write

    store = preference_store or default_preference_store_for_graph_db(db_path)
    with connect_write(str(db_path), purpose="deletion_worker:cycle") as con:
        return run_db_cycle(con, now=now, preference_store=store)
