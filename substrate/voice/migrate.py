"""Migration runner for the voice_note_anchor schema (SPR-02).

Idempotent. Run via the CLI or import ``apply`` from Python:

    python -m substrate.voice.migrate --apply --db-path /path/to.db

Prerequisite check:
    The voice-note rows live in the ``documents`` table (Sprint 13).
    The migration verifies ``documents`` exists before applying. If
    not, it raises a clear error pointing at Sprint 13.

    The sprint spec page describes a ``voice_notes`` table; Antiek
    in fact stores voice notes as documents with
    document_type='voice_note'. The migration enforces what the
    substrate actually requires (``documents``), not what the spec
    page describes. See SCHEMA_NOTES.md for the rationale.

Storage discipline:
    DDL passes through ``runtime/db_lock.connect_write``, same as
    every other writer.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

# Repo root for direct-script invocation.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from runtime.db_lock import LockedConnection, connect_write  # noqa: E402
from substrate.voice.anchor_schema import (  # noqa: E402
    SCHEMA_TABLES,
    VOICE_NOTE_ANCHOR_SCHEMA_SQL,
)


class MissingPrerequisiteError(RuntimeError):
    """Raised when the migration cannot run because an upstream
    schema is absent. The caller should run the upstream migration
    first (Sprint 13 / substrate.graph schema init)."""


def _has_table(con: LockedConnection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name=? LIMIT 1",
        [table],
    ).fetchone()
    return row is not None


def _assert_prerequisites(con: LockedConnection) -> None:
    """Voice notes are stored as documents with
    document_type='voice_note' (Sprint 13). The migration's FKs
    target ``documents`` and ``chunks``; both must exist.

    The spec describes this prerequisite as the ``voice_notes``
    table, but the substrate's actual storage shape is documents.
    Surfacing this discrepancy in the handoff.
    """
    if not _has_table(con, "documents"):
        raise MissingPrerequisiteError(
            "voice_note_anchor migration requires the ``documents`` "
            "table. Voice notes are stored as documents with "
            "document_type='voice_note' (Sprint 13). Run "
            "substrate.graph.schema.init_database_at_path first."
        )
    if not _has_table(con, "chunks"):
        raise MissingPrerequisiteError(
            "voice_note_anchor migration requires the ``chunks`` "
            "table (substrate.graph v1 schema). Run "
            "substrate.graph.schema.init_database_at_path first."
        )


def apply(con: LockedConnection) -> None:
    """Apply the voice_note_anchor migration on a write-locked
    connection. Idempotent.

    Raises ``MissingPrerequisiteError`` if upstream tables are
    absent. The caller (CLI) translates that into a stderr message +
    exit code 2.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"apply() requires a LockedConnection (got "
            f"{type(con).__name__}). Use "
            "runtime.db_lock.connect_write(db_path, purpose=...)."
        )
    _assert_prerequisites(con)
    con.execute(VOICE_NOTE_ANCHOR_SCHEMA_SQL)


def apply_at_path(db_path: str) -> None:
    """Convenience: acquire a write lock and apply the migration."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="voice_anchor_migrate")
    try:
        apply(con)
    finally:
        con.close()


def _main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m substrate.voice.migrate",
        description="Apply the voice_note_anchor migration (SPR-02).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration.",
    )
    p.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to the DuckDB file. Defaults to "
            "ANTIEK_DUCKDB_PATH / substrate.constants.DUCKDB_PATH."
        ),
    )
    args = p.parse_args(argv)
    if not args.apply:
        p.error("specify --apply")
        return 2

    if args.db_path:
        db_path = os.path.expanduser(args.db_path)
    else:
        # Resolve via the same path resolver the graph package uses.
        from substrate.graph import default_db_path
        db_path = default_db_path()

    try:
        apply_at_path(db_path)
    except MissingPrerequisiteError as e:
        sys.stderr.write(f"prerequisite missing: {e}\n")
        return 2

    # Confirm the table is present.
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name=ANY(?) "
            "ORDER BY table_name",
            [list(SCHEMA_TABLES)],
        ).fetchall()
        for r in rows:
            print(f"  {r[0]}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
