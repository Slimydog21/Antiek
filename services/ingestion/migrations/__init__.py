"""Ingestion-specific migrations.

The substrate graph schema is owned by ``substrate/graph/schema.py``;
this module is for tables specific to the ingestion pipeline that
don't belong in the shared graph schema (the operational concerns —
job log, banned-until sentinel — live close to the consumer).

``apply_all(db_path)`` runs every migration in this directory in
filename order. Each migration is idempotent (CREATE IF NOT EXISTS),
so re-running is safe. The pipeline's first DB touch calls
``apply_all`` so the operator never has to remember to run migrations.
"""
from __future__ import annotations

import glob
import os
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))


def _migration_paths() -> list[str]:
    return sorted(glob.glob(os.path.join(_HERE, "*.sql")))


def apply_all(db_path: str, *, _con: Optional[object] = None) -> list[str]:
    """Apply every .sql file in this directory to ``db_path``.

    Returns the list of migration filenames applied. ``_con`` lets a
    caller pass an already-open ``LockedConnection`` (the pipeline
    does this so all schema work happens inside one write lock); the
    leading underscore signals "private — use apply_all(db_path) in
    application code."
    """
    applied: list[str] = []
    if _con is not None:
        for path in _migration_paths():
            with open(path) as f:
                _con.execute(f.read())  # type: ignore[attr-defined]
            applied.append(os.path.basename(path))
        return applied

    # No connection passed — open one ourselves.
    import sys
    _PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
    if _PKG_ROOT not in sys.path:
        sys.path.insert(0, _PKG_ROOT)
    from runtime.db_lock import connect_write  # type: ignore[import-not-found]

    with connect_write(db_path, purpose="ingestion/migrations") as con:
        for path in _migration_paths():
            with open(path) as f:
                con.execute(f.read())
            applied.append(os.path.basename(path))
    return applied
