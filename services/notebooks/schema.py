"""DDL + idempotent migrate for ``services.notebooks`` (SPR-08).

Migrations (applied in order):

- ``0001_per_doc_notebook.sql`` — ``notebook_documents`` +
  ``per_doc_notebook_blocks`` tables (SPR-08 M1, M6).
- ``0002_notebook_blocks.sql`` — provenance + save log (SPR-08 M6, M7).
- ``0003_themes.sql`` — Tier-3 per-theme notebook (SPR-11 M1):
  ``themes`` + ``theme_blocks`` tables.

All go through ``runtime.db_lock.connect_write`` so the
single-writer invariant from ``architecture_notes.md`` §2.3 holds
during DDL.

CLI:

    python -m services.notebooks.migrate --apply
    python -m services.notebooks.migrate --db-path /tmp/test.duckdb --apply
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import duckdb

try:
    from substrate.constants import DUCKDB_PATH
    from runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]
    from substrate.constants import DUCKDB_PATH  # type: ignore[no-redef]


_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


# Applied in declared order; new migrations append. The order is the
# dependency order (0002 references columns that 0001 creates).
MIGRATION_FILES: tuple[str, ...] = (
    "0001_per_doc_notebook.sql",
    "0002_notebook_blocks.sql",
    "0003_themes.sql",
)


def default_db_path() -> str:
    """Resolve the DuckDB path. Mirrors substrate.behavior.schema's
    resolution to keep the operator-overridable env var consistent."""
    explicit = os.environ.get("ANTIEK_DUCKDB_PATH")
    if explicit:
        return os.path.expanduser(explicit)
    return os.path.expanduser(DUCKDB_PATH)


def _read_migration(filename: str) -> str:
    path = os.path.join(_MIGRATIONS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"services.notebooks: migration {filename!r} missing at {path}"
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def init_notebooks_schema(con: LockedConnection) -> None:
    """Apply every notebook migration to ``con``. Idempotent.

    ``con`` must be a ``LockedConnection`` from
    ``runtime.db_lock.connect_write`` so the only-writer invariant
    holds during DDL.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"init_notebooks_schema requires a LockedConnection "
            f"(got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path) or pass the "
            "result into this function."
        )
    for filename in MIGRATION_FILES:
        sql = _read_migration(filename)
        con.execute(sql)


def init_notebooks_schema_at_path(db_path: str) -> None:
    """Convenience: acquire the write lock and apply every migration."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="notebooks_schema_init")
    try:
        init_notebooks_schema(con)
    finally:
        con.close()


def list_notebook_tables(con: "duckdb.DuckDBPyConnection") -> list[str]:
    """Diagnostic: tables this module owns. Used by tests for
    idempotency assertions."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' "
        "  AND table_name IN ('notebook_documents', "
        "                     'per_doc_notebook_blocks', "
        "                     'notebook_block_events', "
        "                     'notebook_save_log', "
        "                     'themes', "
        "                     'theme_blocks') "
        "ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


__all__ = [
    "MIGRATION_FILES",
    "default_db_path",
    "init_notebooks_schema",
    "init_notebooks_schema_at_path",
    "list_notebook_tables",
]
