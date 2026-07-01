"""Allow `failed` deletion-request status on existing DuckDB files."""

from __future__ import annotations

try:
    from ...runtime.db_lock import LockedConnection
except ImportError:  # pragma: no cover - direct-script fallback
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]


_REBUILD_SQL = """
CREATE TABLE deletion_requests_mig (
    request_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'confirmed', 'cancelled', 'completed', 'failed'
    )),
    requested_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason          TEXT
)
"""


def _check_text(con: LockedConnection) -> str:
    try:
        rows = con.execute(
            "SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name = 'deletion_requests' AND constraint_type = 'CHECK'"
        ).fetchall()
    except Exception:
        return ""
    return " ".join(row[0] for row in rows if row and row[0])


def migrate(con: LockedConnection) -> bool:
    """Rebuild deletion_requests iff the live CHECK lacks 'failed'."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "migrate_deletion_requests_failed requires a LockedConnection "
            f"(got {type(con).__name__}); use runtime.db_lock.connect_write."
        )

    exists = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = 'deletion_requests' LIMIT 1"
    ).fetchone()
    if not exists:
        return False
    if "'failed'" in _check_text(con):
        return False

    before = con.execute("SELECT count(*) FROM deletion_requests").fetchone()[0]
    con.execute("BEGIN")
    try:
        con.execute(_REBUILD_SQL)
        con.execute("INSERT INTO deletion_requests_mig BY NAME SELECT * FROM deletion_requests")
        con.execute("DROP TABLE deletion_requests")
        con.execute("ALTER TABLE deletion_requests_mig RENAME TO deletion_requests")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_deletion_requests_user "
            "ON deletion_requests(user_id)"
        )
        after = con.execute("SELECT count(*) FROM deletion_requests").fetchone()[0]
        if before != after:
            raise RuntimeError(
                "deletion_requests failed-status migration row-count mismatch"
            )
    except Exception:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")
    return True

