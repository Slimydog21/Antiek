"""Read-only health probes for the graph DuckDB file.

GF-7 asks for corruption/startup visibility for the substrate's source-of-truth
DuckDB file. DuckDB does not implement SQLite's ``PRAGMA integrity_check`` — it
is not a DuckDB pragma at all, so every attempt raised ``CatalogException`` and
this probe reported ``"unavailable"`` on every build, forever. A field named
``integrity_check`` that can never say ``ok`` reads, on ``/health``, as though a
verification ran and passed; none ever did.

This module now runs a check DuckDB actually implements. For every base table in
``main`` it reads ``pragma_storage_info(<table>)``, which forces DuckDB to parse
that table's per-column block metadata out of the storage layer. That is the
layer where on-disk corruption shows up, and it is metadata-only: cost scales
with column-segment count, not row count, so the probe stays bounded and cheap
enough to run on every ``/health`` hit.

It remains strictly read-only and never raises: a failure is reported as a
value, not an exception.
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


def _storage_integrity(con: duckdb.DuckDBPyConnection) -> str:
    """Verify every base table's storage metadata parses.

    Returns ``"ok"``, ``"empty"`` when the catalog holds no base tables, or
    ``"failed: <where>: <ExcType>"`` naming the first table that would not read.
    Never raises.
    """
    try:
        tables = [
            row[0]
            for row in con.execute(
                "SELECT table_name FROM duckdb_tables() "
                "WHERE database_name = current_database() "
                "AND schema_name = 'main' AND NOT internal "
                "ORDER BY table_name"
            ).fetchall()
        ]
    except Exception as exc:
        return f"failed: catalog: {type(exc).__name__}"

    if not tables:
        return "empty"

    for name in tables:
        # pragma_storage_info takes a string literal, so the identifier is
        # embedded rather than bound; double any quote to keep it one literal.
        literal = name.replace("'", "''")
        try:
            con.execute(
                f"SELECT count(*) FROM pragma_storage_info('{literal}')"
            ).fetchone()
        except Exception as exc:
            return f"failed: {name}: {type(exc).__name__}"

    return "ok"


def probe_duckdb_health(db_path: str) -> DuckDBHealth:
    """Probe ``db_path`` without creating or mutating it.

    The probe proves the file opens read-only, the graph schema sentinel exists,
    DuckDB can read database-size metadata, and that every base table's storage
    metadata parses. It also reports whether a WAL sidecar is present.
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

        integrity_check = _storage_integrity(con)
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

    # "empty" stays passing: a freshly created file with no tables is a valid
    # state for a probe that runs before first init. A "failed: ..." value is
    # real storage-layer corruption and must not be ready.
    integrity_ok = integrity_check in {"ok", "empty"}
    ready = schema_present and database_size_ok and integrity_ok
    if not integrity_ok:
        status = "integrity_failed"
    elif not schema_present:
        status = "schema_missing"
    else:
        status = "ok"
    return DuckDBHealth(
        ready=ready,
        status=status,
        db_path=resolved,
        schema_present=schema_present,
        database_size_ok=database_size_ok,
        integrity_check=integrity_check,
        wal_present=wal_present,
        wal_bytes=wal_bytes,
    )
