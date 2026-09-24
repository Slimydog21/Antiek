"""Merge a staging DuckDB into the live DB in ONE bounded connect_write.

SPR-01 keystone, second half. The corpus ingest writes to a staging DuckDB
(``runtime/staging_db.py``) off the live hot path; this tool copies the
staged rows — documents, book_assets, chunks (with their precomputed
vectors), nodes, and any net-new ip_holders — into the live DB.

The merge is a SINGLE ``runtime.db_lock.connect_write`` transaction: the
live-writer flock opens once, the staging file is ATTACHed read-only, every
table is copied with one ``INSERT … SELECT`` anti-join, and the whole thing
commits or rolls back atomically. That is the keystone property — the
live-writer-held window is bounded to the copy (seconds), not the ingest
(minutes-to-hours), and an interruption mid-merge leaves live exactly at its
pre-merge state, resumable by re-running.

Invariants this tool upholds (see docs/staging_write_map.md):

- **Vectors are COPIED, never recomputed.** The chunk/node vector columns
  are plain DuckDB ``FLOAT[]`` data; the ``INSERT … SELECT`` projects them
  verbatim. There is deliberately no vectorization-model import in this
  module (grep-asserted by the verification gate — the substring that names
  the model layer must not appear here at all).
- **Idempotent on the content-stable id.** Every copy is an anti-join keyed
  on the table's primary key (``document_id`` for documents/book_assets,
  ``chunk_id``/``node_id`` for chunks/nodes, ``display_name`` for
  ip_holders). A re-merge inserts zero rows.
- **Column-explicit, never positional.** The copy is
  ``INSERT INTO t (c1, …, cn) SELECT …`` with the live column list at merge
  time — not ``SELECT s.*``. Each live column is projected by **name** from
  staging (``s.col``) or as ``NULL`` when the column exists only on live
  (prod ``ALTER`` appends / reorders vs fresh ``init_database`` staging).
  Order need not match. :func:`_assert_schema_compatible` aborts only when
  staging lacks a required key / NOT NULL column that cannot be null-filled.

- **Deny-by-default is preserved, not re-decided.** The merge copies whatever
  ``content_class`` the staged document row already carries. It never
  re-classifies rights (that is SPR-02).
- **§16 single-writer.** The only writer touched is live's
  ``connect_write``; staging is ATTACHed READ_ONLY. No second DB engine, no
  scale-out.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import (  # noqa: E402
    connect_write,
    flush_warm_writers,
    process_holds_write_flock,
)

# Merge order is dependency-respecting: ip_holders before documents (so a
# document's ip_holder_id can be remapped to a live holder id), documents
# before book_assets/chunks (FK references), nodes last (no FK to documents
# in the schema, ordered for clarity). Each table is copied with an EXPLICIT
# column list read from the live catalog at merge time (never ``s.*``), under
# a pre-merge names+order check (``_assert_schema_compatible``) so a future
# migration that reorders a live table aborts the merge instead of silently
# shuffling data — see the module docstring + docs/staging_write_map.md.
_DOC_KEYED_TABLES: tuple[tuple[str, str], ...] = (
    ("documents", "document_id"),
    ("book_assets", "document_id"),
    ("chunks", "chunk_id"),
    ("nodes", "node_id"),
)


@dataclass(frozen=True)
class TableMergeResult:
    table: str
    inserted: int
    skipped: int  # staged rows whose id already existed live (idempotency)


@dataclass(frozen=True)
class MergeResult:
    """Outcome of one merge. ``window_s`` is the wall-time the live writer
    lock was held — the keystone number (M6)."""

    tables: tuple[TableMergeResult, ...]
    window_s: float

    @property
    def total_inserted(self) -> int:
        return sum(t.inserted for t in self.tables)

    def render(self) -> str:
        lines = ["merge summary (rows inserted / skipped per table):"]
        for t in self.tables:
            lines.append(f"  {t.table:<14} inserted={t.inserted:<6} skipped={t.skipped}")
        lines.append(f"  connect_write-held window: {self.window_s:.3f}s")
        return "\n".join(lines)


def _attach_literal(path: str) -> str:
    """Quote a filesystem path for use in an ATTACH statement. ATTACH does
    not accept a bind parameter, so the path is a single-quoted SQL literal
    with any interior single-quotes doubled."""
    return path.replace("'", "''")


def _count(con, sql: str, params=None) -> int:
    return int(con.execute(sql, params or []).fetchone()[0])


# Every table the merge copies, in merge order. ``ip_holders`` (keyed on
# display_name, see the write-map) is copied first by _merge_ip_holders; the
# id-keyed tables follow. Derived from _DOC_KEYED_TABLES so the schema-check
# list can never drift from the list actually copied. Used by the pre-merge
# schema check so a divergence is caught before the first insert.
_ALL_MERGED_TABLES: tuple[str, ...] = ("ip_holders",) + tuple(
    t for t, _ in _DOC_KEYED_TABLES
)


def _live_catalog(con) -> str:
    """The default (live) catalog name. DuckDB names it after the DB file's
    basename, so it is ``antiek`` on prod and varies in tests; read it rather
    than hardcode. The ATTACHed staging DB is always the ``staging`` catalog
    (our ATTACH alias)."""
    return con.execute("SELECT current_catalog()").fetchone()[0]


def _ordered_columns(con, table: str, *, catalog: str) -> list[str]:
    """The column names of ``catalog.main.table`` in physical (ordinal) order.

    Read from ``information_schema.columns`` so it reflects the actual catalog,
    not a hand-maintained list that can fall behind a migration. Filter on
    ``table_catalog`` — ``information_schema`` spans EVERY attached database, so
    once staging is ATTACHed both live and staging expose a ``main`` schema and
    a schema-name-only filter would conflate them."""
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position",
        [catalog, table],
    ).fetchall()
    return [r[0] for r in rows]


class SchemaDivergence(RuntimeError):
    """Raised when staging cannot supply required columns for a safe named
    merge (missing PK / NOT NULL without default). Order divergence alone is
    NOT an error — projection is by column name."""


@dataclass(frozen=True)
class _SchemaPlan:
    """Live column order (insert target) + staging column sets (by name)."""

    live_columns: dict[str, list[str]]
    staging_columns: dict[str, frozenset[str]]


# Primary keys that staging MUST have for each merged table.
_TABLE_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "ip_holders": ("ip_holder_id", "display_name"),
    "documents": ("document_id",),
    "book_assets": ("document_id",),
    "chunks": ("chunk_id", "document_id"),
    "nodes": ("node_id",),
}


def _assert_schema_compatible(con) -> _SchemaPlan:
    """Build a name-based merge plan; abort only on missing required columns.

    Long-lived live DBs often diverge in column ORDER (and gain live-only
    columns via ``ALTER TABLE … ADD COLUMN``) relative to a freshly
    ``init_database``-bootstrapped staging file. Explicit named projection
    makes order irrelevant; live-only nullable columns are null-filled.
    """
    live_catalog = _live_catalog(con)
    live_cols: dict[str, list[str]] = {}
    staging_cols: dict[str, frozenset[str]] = {}
    problems: list[str] = []
    for table in _ALL_MERGED_TABLES:
        live = _ordered_columns(con, table, catalog=live_catalog)
        staged = _ordered_columns(con, table, catalog="staging")
        live_cols[table] = live
        staging_cols[table] = frozenset(staged)
        if not staged:
            problems.append(f"  {table}: missing from staging")
            continue
        for key in _TABLE_REQUIRED_KEYS.get(table, ()):
            if key not in staging_cols[table]:
                problems.append(
                    f"  {table}: staging missing required column {key!r} "
                    f"(live={live} staging={staged})"
                )
        # NOT NULL live columns without a default must exist on staging
        for col, nullable, default in _column_nullability(
            con, table, catalog=live_catalog
        ):
            if col not in staging_cols[table] and nullable == "NO" and default is None:
                problems.append(
                    f"  {table}: staging missing NOT NULL column {col!r} "
                    f"(cannot null-fill)"
                )
    if problems:
        raise SchemaDivergence(
            "staging/live schema incompatible — refusing to merge. "
            "Staging is missing required columns (order differences are OK; "
            "re-bootstrap staging or null-fill only applies to nullable "
            "live-only columns). Problems:\n" + "\n".join(problems)
        )
    return _SchemaPlan(live_columns=live_cols, staging_columns=staging_cols)


def _column_nullability(
    con, table: str, *, catalog: str
) -> list[tuple[str, str, str | None]]:
    """Return (column_name, is_nullable YES/NO, column_default) for ``table``."""
    rows = con.execute(
        "SELECT column_name, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position",
        [catalog, table],
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def merge_staging(
    *,
    live_db: str,
    staging_db: str,
    fail_after_attach: bool = False,
) -> MergeResult:
    """Copy net-new staged rows into the live DB in one ``connect_write``.

    ``fail_after_attach`` is a test-only hook: when True, an exception is
    raised *inside* the open transaction (after some inserts) to exercise the
    atomic-rollback path. Production callers never set it.

    Returns a :class:`MergeResult` with per-table insert/skip counts and the
    measured live-writer-held window.
    """
    staging_db = os.path.abspath(os.path.expanduser(staging_db))
    if not os.path.exists(staging_db):
        raise FileNotFoundError(f"staging DB not found: {staging_db}")

    attach_lit = _attach_literal(staging_db)
    results: list[TableMergeResult] = []

    # The keystone window is live-writer-HELD time, as seen by other
    # processes waiting on the flock. If this process already holds the live
    # flock at entry — an active writer elsewhere in the process, a parked
    # (warm) writer, or one whose expiry close is in flight — every second
    # from here on is held time, the wait for the in-process gate included,
    # so the clock starts now. Otherwise it starts once the live DB is
    # actually opened (after the staging close, during which the flock is
    # free). The check is repeated under the gate: a writer that parks
    # during our gate wait was holding the flock the whole time.
    started = time.monotonic()
    live_flock_held_at_entry = process_holds_write_flock(live_db)

    def _release_staging_writer() -> None:
        # Runs under db_lock's in-process write gate, before the live flock
        # is taken. The ingest that staged these rows runs in this process
        # and db_lock parks its writer for the keepalive window (WP-3,
        # default 20 s); DuckDB refuses to ATTACH a file the process already
        # holds open ("Unique file handle conflict"), so close that parked
        # writer here. The merge only reads staging, so nothing is lost.
        # Under the gate no other thread can re-park it before the ATTACH,
        # and flush_warm_writers waits for a close the keepalive expiry
        # timer has already started (or raises, and nothing is opened).
        #
        # A parked live writer is kept and reused rather than released: on
        # a production-scale DB a cold reopen costs the documented ~6.8 s
        # (db_lock WP-3) inside the window, while the staging close costs
        # one ingest round's checkpoint (~20 ms on the test fixture).
        nonlocal started
        live_flock_held = live_flock_held_at_entry or process_holds_write_flock(live_db)
        flush_warm_writers(staging_db)
        if not live_flock_held:
            started = time.monotonic()

    # The ONE write window. Everything below holds the live flock; it opens
    # once (connect_write) and closes once (the `with` exit). Wall-time of
    # this block is the keystone window.
    with connect_write(
        live_db, purpose="merge_staging", before_open=_release_staging_writer
    ) as con:
        con.execute(f"ATTACH '{attach_lit}' AS staging (READ_ONLY)")
        try:
            plan = _assert_schema_compatible(con)

            # Explicit transaction so a mid-merge failure rolls back ALL
            # tables atomically — live is never left half-merged.
            con.execute("BEGIN TRANSACTION")
            try:
                holders = _merge_ip_holders(
                    con,
                    columns=plan.live_columns["ip_holders"],
                    staging_columns=plan.staging_columns["ip_holders"],
                )
                results.append(holders)

                staged_holder_remap = _build_holder_remap(con)
                for table, key in _DOC_KEYED_TABLES:
                    res = _merge_table(
                        con,
                        table=table,
                        key=key,
                        columns=plan.live_columns[table],
                        staging_columns=plan.staging_columns[table],
                    )
                    results.append(res)
                    if table == "documents" and staged_holder_remap:
                        _remap_document_ip_holders(con, staged_holder_remap)

                if fail_after_attach:
                    raise RuntimeError(
                        "injected mid-merge failure (test hook) — must roll back"
                    )

                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            con.execute("DETACH staging")
    window_s = time.monotonic() - started

    return MergeResult(tables=tuple(results), window_s=window_s)


def _projection(
    live_columns: list[str], staging_columns: frozenset[str] | set[str]
) -> tuple[str, str]:
    """Build insert target list (live order) and SELECT list by name.

    Staging columns are referenced as ``s.col``; live-only columns become
    ``NULL AS col`` so prod ALTERs (e.g. ``owner_user_id`` / ``structured_blocks``)
    do not block merge against a fresh staging schema.
    """
    target = ", ".join(live_columns)
    select_parts: list[str] = []
    for col in live_columns:
        if col in staging_columns:
            select_parts.append(f"s.{col}")
        else:
            select_parts.append(f"NULL AS {col}")
    return target, ", ".join(select_parts)



def _merge_table(
    con,
    *,
    table: str,
    key: str,
    columns: list[str],
    staging_columns: frozenset[str] | set[str],
) -> TableMergeResult:
    """Anti-join copy of one table on its primary key. Columns are projected
    by name from staging (``NULL`` for live-only cols). Uses ``RETURNING`` for
    net-new count; skipped = staged - inserted."""
    target, select = _projection(columns, staging_columns)
    staged_total = _count(con, f"SELECT COUNT(*) FROM staging.{table}")
    inserted_rows = con.execute(
        f"INSERT INTO {table} ({target}) "
        f"SELECT {select} FROM staging.{table} s "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} l WHERE l.{key} = s.{key}) "
        f"RETURNING {key}"
    ).fetchall()
    inserted = len(inserted_rows)
    return TableMergeResult(
        table=table, inserted=inserted, skipped=staged_total - inserted
    )


def _merge_ip_holders(
    con,
    *,
    columns: list[str],
    staging_columns: frozenset[str] | set[str],
) -> TableMergeResult:
    """Insert net-new ip_holders keyed on ``display_name`` (not the random
    id). A holder already present live is authoritative and left untouched —
    its escrow balance is never overwritten by a staged copy. Column-explicit
    by name (same as :func:`_merge_table`)."""
    target, select = _projection(columns, staging_columns)
    staged_total = _count(con, "SELECT COUNT(*) FROM staging.ip_holders")
    inserted_rows = con.execute(
        f"INSERT INTO ip_holders ({target}) "
        f"SELECT {select} FROM staging.ip_holders s "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM ip_holders l WHERE l.display_name = s.display_name"
        ") "
        "RETURNING ip_holder_id"
    ).fetchall()
    inserted = len(inserted_rows)
    return TableMergeResult(
        table="ip_holders", inserted=inserted, skipped=staged_total - inserted
    )


def _build_holder_remap(con) -> dict[str, str]:
    """Map each staging ip_holder_id → the LIVE ip_holder_id for the same
    display_name. After ``_merge_ip_holders`` every staged display_name has a
    live row (either pre-existing or just inserted), so this is total over
    staged holders. The remap is applied only to documents this merge
    inserts."""
    rows = con.execute(
        "SELECT s.ip_holder_id, l.ip_holder_id "
        "FROM staging.ip_holders s "
        "JOIN ip_holders l ON l.display_name = s.display_name"
    ).fetchall()
    return {staging_id: live_id for staging_id, live_id in rows if staging_id != live_id}


def _remap_document_ip_holders(con, remap: dict[str, str]) -> None:
    """Repoint documents.ip_holder_id from a staging holder id to the live
    holder id for the same publisher. Touches only rows currently carrying a
    staging id (the ones this merge just inserted); idempotent on re-run
    because after the first remap no document carries a staging-only id.

    DuckDB refuses to UPDATE a secondary-indexed column on a row referenced
    by a foreign key (chunks/book_assets reference documents), which is why
    ``substrate/graph/schema.py`` does not index ``documents.ip_holder_id`` and
    DROPS ``idx_documents_ip_holder`` at init. The DROP here is defensive for a
    live file that still carries the legacy index. The index is deliberately
    NOT re-created afterwards: re-creating it re-armed that failure for every
    later holder write on a chunked document (the SPR-08 ip_holder persist
    path and ``tools/backfill_ip_holders.py``), while the warm schema probe
    reported the file as current."""
    con.execute("DROP INDEX IF EXISTS idx_documents_ip_holder")
    for staging_id, live_id in remap.items():
        con.execute(
            "UPDATE documents SET ip_holder_id = ? WHERE ip_holder_id = ?",
            [live_id, staging_id],
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.merge_staging",
        description=(
            "Merge a staging DuckDB (written by run_corpus_ingest --staging-db) "
            "into the live DB in one bounded connect_write transaction. The "
            "live API stays readable; only this merge holds the live writer."
        ),
    )
    p.add_argument("--live-db", required=True, help="the live DuckDB to merge into")
    p.add_argument("--staging-db", required=True, help="the staging DuckDB to merge from")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = merge_staging(live_db=args.live_db, staging_db=args.staging_db)
    print(result.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
