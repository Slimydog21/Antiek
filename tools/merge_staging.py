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
from typing import Optional

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402


# Merge order is dependency-respecting: ip_holders before documents (so a
# document's ip_holder_id can be remapped to a live holder id), documents
# before book_assets/chunks (FK references), nodes last (no FK to documents
# in the schema, ordered for clarity). Each table copies its full row set
# (``s.*``) anti-joined on its PK so the column list can never drift from the
# live schema (no hand-maintained column lists to fall behind a migration).
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

    # The ONE write window. Everything below holds the live flock; it opens
    # once (connect_write) and closes once (the `with` exit). Wall-time of
    # this block is the keystone window.
    started = time.monotonic()
    with connect_write(live_db, purpose="merge_staging") as con:
        con.execute(f"ATTACH '{attach_lit}' AS staging (READ_ONLY)")
        try:
            # Explicit transaction so a mid-merge failure rolls back ALL
            # tables atomically — live is never left half-merged.
            con.execute("BEGIN TRANSACTION")
            try:
                # 1) ip_holders: insert net-new holders keyed on display_name
                #    (the logical identity; the id is a random UUID per the
                #    write-map). Then remap each merged document's ip_holder_id
                #    to the LIVE holder id for its display_name, so re-ingesting
                #    the same publisher does not fan out into duplicate escrow
                #    accounts and a dangling staging id never reaches live.
                holders = _merge_ip_holders(con)
                results.append(holders)

                # 2) documents → book_assets → chunks → nodes, each an
                #    anti-join on its PK. ip_holder_id remap happens after the
                #    documents copy (the remap targets only the rows this merge
                #    just inserted, by staging holder id).
                staged_holder_remap = _build_holder_remap(con)
                for table, key in _DOC_KEYED_TABLES:
                    res = _merge_table(con, table=table, key=key)
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


def _merge_table(con, *, table: str, key: str) -> TableMergeResult:
    """Anti-join copy of one table on its primary key. Uses ``RETURNING`` to
    get the exact net-new count, and computes skipped = (staged rows) -
    (inserted) so the per-table summary is honest about idempotency."""
    staged_total = _count(con, f"SELECT COUNT(*) FROM staging.{table}")
    inserted_rows = con.execute(
        f"INSERT INTO {table} "
        f"SELECT s.* FROM staging.{table} s "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} l WHERE l.{key} = s.{key}) "
        f"RETURNING {key}"
    ).fetchall()
    inserted = len(inserted_rows)
    return TableMergeResult(
        table=table, inserted=inserted, skipped=staged_total - inserted
    )


def _merge_ip_holders(con) -> TableMergeResult:
    """Insert net-new ip_holders keyed on ``display_name`` (not the random
    id). A holder already present live is authoritative and left untouched —
    its escrow balance is never overwritten by a staged copy."""
    staged_total = _count(con, "SELECT COUNT(*) FROM staging.ip_holders")
    inserted_rows = con.execute(
        "INSERT INTO ip_holders "
        "SELECT s.* FROM staging.ip_holders s "
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

    ``documents.ip_holder_id`` is an indexed column, and DuckDB 1.5.2 refuses
    to UPDATE a secondary-indexed column on a row referenced by a foreign key
    (chunks/book_assets reference documents). Reuse the substrate's sanctioned
    workaround: drop the index, UPDATE, recreate — all inside this one
    transaction so it stays atomic and invisible to readers."""
    con.execute("DROP INDEX IF EXISTS idx_documents_ip_holder")
    try:
        for staging_id, live_id in remap.items():
            con.execute(
                "UPDATE documents SET ip_holder_id = ? WHERE ip_holder_id = ?",
                [live_id, staging_id],
            )
    finally:
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_ip_holder "
            "ON documents(ip_holder_id)"
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


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = merge_staging(live_db=args.live_db, staging_db=args.staging_db)
    print(result.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
