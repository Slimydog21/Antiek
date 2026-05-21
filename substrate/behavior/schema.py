"""DDL + migrate command for the Tier-1 behavior store (SPR-01 M2).

Loads the migration SQL files from ``substrate/behavior/migrations/``
and applies them through ``runtime.db_lock.connect_write`` — the
only-writer invariant from ``architecture_notes.md`` §2.3.

Two entry points:

- ``init_behavior_schema(con)`` — apply against an already-held
  LockedConnection (used inside larger init flows).
- ``init_behavior_schema_at_path(db_path)`` — acquire the write
  lock and apply (used by the CLI and tests).

Both are idempotent. Every CREATE in the .sql files uses
IF NOT EXISTS; re-running is safe.

CLI:

    python -m substrate.behavior.migrate --apply
    python -m substrate.behavior.migrate --db-path /tmp/test.duckdb --apply

The CLI lives at ``substrate/behavior/migrate.py`` (a thin wrapper
around this module) so the verification gate's
``python -m substrate.behavior.migrate --apply`` works.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import duckdb

try:
    from ..constants import DUCKDB_PATH
    from ...runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]
    from substrate.constants import DUCKDB_PATH  # type: ignore[no-redef]


_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

# Migration files in apply order. New migrations append; the order
# is the dependency order (consent depends on the behavior_events
# table being present? — no, they are independent today but we keep
# the order stable).
MIGRATION_FILES: tuple[str, ...] = (
    "0001_behavior_store.sql",
    "0002_user_consent.sql",
)


def default_db_path() -> str:
    """Resolve the DuckDB path the behavior store writes to.

    Resolution order mirrors ``substrate/graph/__init__.py``:

    1. ``ANTIEK_DUCKDB_PATH`` env var (operator override).
    2. ``substrate.constants.DUCKDB_PATH`` expanded via ``~``.
    """
    explicit = os.environ.get("ANTIEK_DUCKDB_PATH")
    if explicit:
        return os.path.expanduser(explicit)
    return os.path.expanduser(DUCKDB_PATH)


def _read_migration(filename: str) -> str:
    path = os.path.join(_MIGRATIONS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"behavior schema: migration {filename!r} missing at {path}"
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def init_behavior_schema(con: LockedConnection) -> None:
    """Apply every behavior-store migration to ``con``. Idempotent.

    ``con`` must be a ``LockedConnection`` from
    ``runtime.db_lock.connect_write`` so the only-writer invariant
    holds during DDL.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"init_behavior_schema requires a LockedConnection "
            f"(got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path) or pass the "
            "result into this function."
        )
    for filename in MIGRATION_FILES:
        sql = _read_migration(filename)
        con.execute(sql)


def init_behavior_schema_at_path(db_path: str) -> None:
    """Convenience: acquire the write lock and apply every migration.

    Used by the CLI + tests. Production callers manage their own
    lock lifecycles and call ``init_behavior_schema`` directly.
    """
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="behavior_schema_init")
    try:
        init_behavior_schema(con)
    finally:
        con.close()


def list_behavior_tables(con: "duckdb.DuckDBPyConnection") -> list[str]:
    """Return only the tables this module owns. Used by tests to
    assert migration idempotency."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' "
        "  AND table_name IN ('behavior_events', "
        "                     'user_behavior_consent', "
        "                     'dp_shuffler_batches') "
        "ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]
