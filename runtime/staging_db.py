"""Staging DuckDB for off-hot-path corpus ingest (SPR-01 keystone).

The corpus ingest's slow work — download, extract, chunk, embed — used to
run *inside* the live single-writer lock, so every batch stopped the API
for the whole ingest duration. This module gives the ingest a separate
DuckDB file to write to while the live API keeps serving the live DB; a
brief merge (`tools/merge_staging.py`) then copies the staged rows into
live through ONE `runtime.db_lock.connect_write` transaction.

Two things this module owns:

1. **A schema-identical staging file.** The staging schema is not a
   hand-copied DDL that can drift from live — `prepare_staging_db` runs the
   exact same `substrate.graph.schema.init_database` against the staging
   file. Same DDL, same tables, same column types, by construction. If the
   live schema gains a column tomorrow, staging gains it the same day with
   no edit here.

2. **Routing the orchestrator's write target.** Staging mode is not a new
   write path — it is the *existing* ingest pointed at a different file.
   `resolve_ingest_target` takes the `--staging-db` flag and returns the
   path the connectors' `connect_write` calls should target. The connectors
   are untouched: they already accept a `db_path`; staging mode only changes
   which path they get.

§16 discipline: staging is a plain DuckDB file written through the same
single-writer flock (`connect_write`) as live. No second runtime, no second
DB engine, no scale-out. The merge — not the ingest — is the only thing that
ever touches the live writer.
"""

from __future__ import annotations

import os
from typing import Optional

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database


def prepare_staging_db(staging_path: str) -> str:
    """Create-or-open the staging DuckDB at ``staging_path`` with a schema
    derived from the live schema, and return the resolved absolute path.

    The schema is bootstrapped by running the canonical
    ``substrate.graph.schema.init_database`` — the same idempotent DDL that
    builds the live DB — so the staging schema cannot diverge from live.
    Idempotent: re-preparing an existing staging file is a no-op (every
    CREATE is ``IF NOT EXISTS``), which is what lets a long ingest resume
    appending to the same staging file across runs.

    Goes through ``connect_write`` so even the staging file obeys the
    single-writer flock discipline (a second ingest process pointed at the
    same staging file serializes rather than corrupting it).
    """
    resolved = os.path.abspath(os.path.expanduser(staging_path))
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(resolved, purpose="staging_schema_init")
    try:
        init_database(con)
    finally:
        con.close()
    return resolved


def resolve_ingest_target(
    *, db_path: Optional[str], staging_db: Optional[str]
) -> str:
    """Resolve the path the ingest should write to.

    - ``staging_db`` set → staging mode: prepare the staging file (schema
      bootstrap) and return its path. NO write will hit the live DB during
      the ingest; the live DB stays readable and the merge is the only step
      that touches the live writer.
    - ``staging_db`` unset → the legacy direct-write path: return ``db_path``
      unchanged (the orchestrator's existing prod-write guard still applies).

    Returns the resolved write-target path. Raises ``ValueError`` if neither
    is set (a real run must have a target).
    """
    if staging_db:
        return prepare_staging_db(staging_db)
    if not db_path:
        raise ValueError(
            "resolve_ingest_target: a real ingest needs either --staging-db "
            "or --db-path."
        )
    return db_path


def is_staging_mode(staging_db: Optional[str]) -> bool:
    """True iff the run is in staging mode. Trivial, but named so call sites
    read as intent rather than a truthiness check on a flag."""
    return bool(staging_db)
