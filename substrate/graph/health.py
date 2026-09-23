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

SPR-11 Task 4 adds three read-only account-memory (v10) schema postconditions
to the same snapshot. They reuse the predicates the migration itself asserts
with -- ``_nodes_have_memory`` / ``_edges_have_owner`` / ``_owner_index_exists``
from ``substrate.graph.migrate_v10_account_memory`` -- rather than restating the
SQL here, so ``/health`` and the migration can never disagree about what "v10
applied" means. Nothing here runs the migration: the predicates are pure
``SELECT``s against catalog views, they run on the connection this probe has
already opened, and the whole snapshot is cached at app startup. Opening a
second connection per request would be both a writer-lock conflict and a
single-writer violation.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, cast

from runtime.db_lock import LockedConnection, ReadConnection, connect_read
from substrate.graph.migrate_v10_account_memory import (
    _edges_have_owner,
    _nodes_have_memory,
    _owner_index_exists,
)


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
    # SPR-11 v10 account-memory schema postconditions. Read-only and reported
    # independently of `ready`: a database can be perfectly healthy and simply
    # not have had the explicit, operator-run v10 migration applied yet, which
    # is exactly the state these three fields exist to make visible.
    memory_nodes_ready: bool = False
    memory_edges_owner_ready: bool = False
    memory_owner_index_ready: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _wal_path(db_path: str) -> str:
    return db_path + ".wal"


def _storage_integrity(con: ReadConnection) -> str:
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


def _memory_postconditions(con: ReadConnection) -> tuple[bool, bool, bool]:
    """Evaluate the three v10 account-memory schema postconditions.

    Returns ``(nodes_ready, edges_owner_ready, owner_index_ready)``. Each
    predicate is evaluated independently and a raise is reported as ``False``
    for that field alone: the migration's predicates raise on shapes they do
    not recognize, and an unrecognized shape is precisely "this postcondition
    is not satisfied" -- it must not blank the other two, and it must never
    escape a probe whose contract is that it never raises.

    The predicates are typed against ``LockedConnection`` because the migration
    calls them under the serialized writer. They issue nothing but ``SELECT``s
    against ``information_schema`` / ``duckdb_constraints()`` / ``duckdb_indexes()``,
    so the read-only handle this probe already holds satisfies every attribute
    they touch; the cast records that deliberately rather than widening the
    migration's own signature.
    """
    read_con = cast(LockedConnection, con)
    results: list[bool] = []
    for predicate in (_nodes_have_memory, _edges_have_owner, _owner_index_exists):
        try:
            results.append(bool(predicate(read_con)))
        except Exception:
            results.append(False)
    return results[0], results[1], results[2]


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
        con = connect_read(resolved)
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
    memory_nodes_ready = False
    memory_edges_owner_ready = False
    memory_owner_index_ready = False
    try:
        row = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'nodes'"
        ).fetchone()
        schema_present = bool(row and row[0] > 0)

        con.execute("PRAGMA database_size").fetchone()
        database_size_ok = True

        integrity_check = _storage_integrity(con)

        # Same connection, no writes, no migration. Skipped entirely when the
        # graph schema is absent: with no `nodes`/`edges` there is nothing for
        # the postconditions to be about, and False is the honest answer.
        if schema_present:
            (
                memory_nodes_ready,
                memory_edges_owner_ready,
                memory_owner_index_ready,
            ) = _memory_postconditions(con)
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
            memory_nodes_ready=memory_nodes_ready,
            memory_edges_owner_ready=memory_edges_owner_ready,
            memory_owner_index_ready=memory_owner_index_ready,
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
        memory_nodes_ready=memory_nodes_ready,
        memory_edges_owner_ready=memory_edges_owner_ready,
        memory_owner_index_ready=memory_owner_index_ready,
    )
