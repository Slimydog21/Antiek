"""Read-only health probes for the graph DuckDB file.

GF-7 asks for corruption/startup visibility for the substrate's source-of-truth
DuckDB file. DuckDB's Python build in current CI does not expose SQLite-style
``PRAGMA integrity_check``; when unavailable, this module reports that fact
explicitly instead of pretending a full page-integrity scan ran.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

import duckdb


@dataclass(frozen=True)
class DuckDBHealth:
    """JSON-serializable DuckDB health snapshot."""

    ready: bool
    status: str
    db_path: str
    schema_present: bool = False
    database_size_ok: bool = False
    integrity_check: str = "not_run"
    wal_present: bool = False
    wal_bytes: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _wal_path(db_path: str) -> str:
    return db_path + ".wal"


def probe_duckdb_health(db_path: str) -> DuckDBHealth:
    """Probe ``db_path`` without creating or mutating it.

    The probe proves the file opens read-only, the graph schema sentinel exists,
    DuckDB can read database-size metadata, and whether a WAL sidecar is present.
    It attempts ``PRAGMA integrity_check`` opportunistically and reports
    ``"unavailable"`` on DuckDB builds that do not implement it.
    """
    resolved = os.path.abspath(os.path.expanduser(db_path))
    wal_path = _wal_path(resolved)
    wal_present = os.path.exists(wal_path)
    wal_bytes = os.path.getsize(wal_path) if wal_present else 0

    if not os.path.exists(resolved):
        return DuckDBHealth(
            ready=False,
            status="missing",
            db_path=resolved,
            wal_present=wal_present,
            wal_bytes=wal_bytes,
            error="DuckDB file does not exist",
        )

    try:
        con = duckdb.connect(resolved, read_only=True)
    except Exception as exc:
        return DuckDBHealth(
            ready=False,
            status="open_failed",
            db_path=resolved,
            wal_present=wal_present,
            wal_bytes=wal_bytes,
            error=f"{type(exc).__name__}: {exc}",
        )

    schema_present = False
    database_size_ok = False
    integrity_check = "not_run"
    try:
        row = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'nodes'"
        ).fetchone()
        schema_present = bool(row and row[0] > 0)

        con.execute("PRAGMA database_size").fetchone()
        database_size_ok = True

        try:
            rows = con.execute("PRAGMA integrity_check").fetchall()
        except duckdb.CatalogException:
            integrity_check = "unavailable"
        else:
            integrity_check = "ok" if rows else "empty_result"
    except Exception as exc:
        return DuckDBHealth(
            ready=False,
            status="probe_failed",
            db_path=resolved,
            schema_present=schema_present,
            database_size_ok=database_size_ok,
            integrity_check=integrity_check,
            wal_present=wal_present,
            wal_bytes=wal_bytes,
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        con.close()

    ready = schema_present and database_size_ok and integrity_check in {
        "ok",
        "unavailable",
    }
    return DuckDBHealth(
        ready=ready,
        status="ok" if ready else "schema_missing",
        db_path=resolved,
        schema_present=schema_present,
        database_size_ok=database_size_ok,
        integrity_check=integrity_check,
        wal_present=wal_present,
        wal_bytes=wal_bytes,
    )
