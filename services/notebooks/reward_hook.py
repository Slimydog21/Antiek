"""Reward-proxy backfill hook (SPR-08 M7).

Bridges the per-document notebook surface (SPR-08) to the
medium-horizon reward proxy worker (SPR-01 substrate). The contract
lives in ``services/notebooks/REWARD_HOOK.md``; this module is the
implementation.

Two responsibilities:

1. ``check_reward_join`` — read-only diagnostic the FastAPI layer
   exposes for the operator dashboard. Given an ``event_id``, returns
   the notebook blocks (if any) that cite it. Used by the M7
   verification gate.

2. ``run_medium_backfill`` — actually executes the canonical join
   from ``REWARD_PROXY.md`` §Worker 2 against ``behavior_events``.
   This is what makes the previously-stub
   ``substrate/behavior/workers/reward_medium.py`` a real worker;
   that module now delegates to this function when the notebook
   tables are present.

No emit
-------
This module does NOT emit behavior events. The block→event link IS
the record; emitting a paper event for the link would double-count
in the reward join. The auto-populator writes
``notebook_block_events``; this module reads.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

import duckdb

try:
    from runtime.db_lock import connect_write
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from services.notebooks.schema import default_db_path  # type: ignore[no-redef]


# ── Diagnostics ──


@dataclass(frozen=True)
class BlockLink:
    """One block that cites a behavior event."""

    block_id: str
    notebook_id: str
    block_type: str
    document_id: Optional[str]


@dataclass(frozen=True)
class BackfillResult:
    """Returned by ``run_medium_backfill``."""

    status: str  # "ran" | "skipped_no_notebooks" | "skipped_tables_missing"
    rows_updated: int
    reason: str = ""


# ── Connection helpers ──


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Same pattern as substrate.behavior.export — not read_only=True
    so concurrent writers in the same process don't crash on
    DuckDB's read-mode mutex."""
    return duckdb.connect(db_path)


def _table_present(db_path: str, name: str) -> bool:
    con = _connect_for_read(db_path)
    try:
        row = con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name = ?",
            [name],
        ).fetchone()
        return row is not None
    finally:
        con.close()


REQUIRED_TABLES: tuple[str, ...] = (
    "behavior_events",
    "notebook_documents",
    "per_doc_notebook_blocks",
)


# ── Read-side diagnostic ──


def check_reward_join(
    event_id: str,
    *,
    db_path: Optional[str] = None,
) -> list[BlockLink]:
    """Return every notebook block whose source_event_ids includes
    ``event_id``.

    Used by the operator dashboard to validate the substrate's
    reward signal. Returns an empty list if no block cites the
    event — that's the steady-state for un-notebooked events.

    The join goes through ``notebook_block_events`` (the normalised
    table) rather than parsing ``per_doc_notebook_blocks.source_event_ids``;
    the JSON-array path is a performance trap on large notebooks.
    """
    path = db_path or default_db_path()
    if not (
        _table_present(path, "notebook_block_events")
        and _table_present(path, "per_doc_notebook_blocks")
    ):
        return []
    con = _connect_for_read(path)
    try:
        rows = con.execute(
            "SELECT nb.block_id, nb.notebook_id, nb.block_type, nb.document_id "
            "FROM notebook_block_events nbe "
            "JOIN per_doc_notebook_blocks nb USING (block_id) "
            "WHERE nbe.event_id = ?",
            [event_id],
        ).fetchall()
    finally:
        con.close()
    return [
        BlockLink(
            block_id=r[0],
            notebook_id=r[1],
            block_type=r[2],
            document_id=r[3],
        )
        for r in rows
    ]


# ── Medium-horizon backfill ──


def run_medium_backfill(
    *,
    db_path: Optional[str] = None,
    window_days: int = 30,
    max_refs: int = 5,
) -> BackfillResult:
    """Execute the canonical join from REWARD_PROXY.md §Worker 2.

    Side-effect: rows in ``behavior_events`` whose
    ``reward_proxy_medium`` is NULL and whose
    ``(user_id, document_id)`` appears in a per-doc notebook within
    ``window_days`` of the event timestamp get
    ``reward_proxy_medium = LEAST(ref_count, max_refs) / max_refs``.

    The function is idempotent: re-running on the same DB does
    nothing because the WHERE clause filters on
    ``reward_proxy_medium IS NULL``.

    Returns:
        ``BackfillResult`` with row count + status. ``skipped_*``
        statuses are not errors — they mean the substrate isn't yet
        in a state where the join can fire (no notebooks yet, or
        SPR-01 isn't applied to this DB).
    """
    path = db_path or default_db_path()
    for required in REQUIRED_TABLES:
        if not _table_present(path, required):
            return BackfillResult(
                status="skipped_tables_missing",
                rows_updated=0,
                reason=(
                    f"required table {required!r} not present in {path}. "
                    "Apply substrate.behavior.migrate and "
                    "services.notebooks.migrate before backfilling."
                ),
            )

    # Short-circuit if no notebooks at all. The UPDATE would no-op
    # but we surface a clean "skipped_no_notebooks" status so cron
    # logs are readable.
    con_r = _connect_for_read(path)
    try:
        nb_count = con_r.execute(
            "SELECT COUNT(*) FROM notebook_documents"
        ).fetchone()[0]
    finally:
        con_r.close()
    if not nb_count:
        return BackfillResult(
            status="skipped_no_notebooks",
            rows_updated=0,
            reason="no notebooks present; nothing to backfill",
        )

    # The DDL of behavior_events stores timestamps as TIMESTAMP, so
    # the INTERVAL clause works directly. We reproduce the literal
    # query from REWARD_PROXY.md as closely as DuckDB syntax allows.
    sql = f"""
    WITH per_doc_refs AS (
      SELECT
        nd.user_id AS user_id,
        nb.document_id AS document_id,
        COUNT(*) AS ref_count,
        MIN(nb.created_at) AS first_ref_at
      FROM notebook_documents nd
      JOIN per_doc_notebook_blocks nb ON nb.notebook_id = nd.notebook_id
      WHERE nb.document_id IS NOT NULL
      GROUP BY 1, 2
    )
    UPDATE behavior_events
    SET reward_proxy_medium = LEAST(refs.ref_count, {int(max_refs)}) / {float(max_refs)}
    FROM per_doc_refs refs
    WHERE behavior_events.user_id = refs.user_id
      AND behavior_events.document_id = refs.document_id
      AND behavior_events.reward_proxy_medium IS NULL
      AND refs.first_ref_at <= behavior_events.timestamp_utc
                                + INTERVAL {int(window_days)} DAY;
    """

    con = connect_write(path, purpose="reward_medium_backfill")
    try:
        # DuckDB's UPDATE doesn't return a row count directly; we
        # query the change_count via a follow-up SELECT against the
        # affected rows. The simpler path is to count the candidate
        # rows BEFORE + AFTER and diff.
        before = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE reward_proxy_medium IS NOT NULL"
        ).fetchone()[0]
        con.execute(sql)
        after = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE reward_proxy_medium IS NOT NULL"
        ).fetchone()[0]
        delta = int(after) - int(before)
    finally:
        con.close()

    return BackfillResult(status="ran", rows_updated=max(delta, 0))


__all__ = [
    "BackfillResult",
    "BlockLink",
    "REQUIRED_TABLES",
    "check_reward_join",
    "run_medium_backfill",
]
