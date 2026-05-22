"""Deep-horizon reward proxy backfill worker (SPR-01 M5, made REAL
2026-05-22).

Joins the four-table chain documented in REWARD_PROXY.md §Worker 3:

    behavior_events
        ↓ source_event_ids on
    per_doc_notebook_blocks
        ↓ notebook_id on
    deliverable_citations
        ↓ deliverable_id on
    deliverables (status='published')

For every behavior event whose source notebook is cited by a published
deliverable, set ``reward_proxy_deep = 1.0`` if not already set.

Idempotent: only updates rows whose ``reward_proxy_deep`` is NULL or
zero, and only when at least one published-deliverable citation exists.
Re-running the worker re-discovers no new rows once the corpus is
stable.

The 1.0 shaping is intentionally binary today — publication is the
threshold. Future work shapes by deliverable reach (views, citations,
etc.); the metadata column on deliverables is the carrier.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

import duckdb

try:
    from ..schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    return duckdb.connect(db_path)


# Schema requirements before the worker can run.
REQUIRED_TABLES: tuple[str, ...] = (
    "notebook_documents",
    "per_doc_notebook_blocks",
    "deliverables",
    "deliverable_citations",
)


@dataclass(frozen=True)
class DeepBackfillResult:
    """Diagnostic returned by ``run_reward_deep_backfill``."""

    status: str  # "deferred" | "ran" | "empty"
    reason: str
    rows_updated: int = 0


def _tables_present(db_path: str, names: tuple[str, ...]) -> tuple[str, ...]:
    con = _connect_for_read(db_path)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main'"
        ).fetchall()
    finally:
        con.close()
    present = {r[0] for r in rows}
    return tuple(n for n in names if n in present)


# The reward_deep join, in SQL. Walks event → block → notebook →
# deliverable_citation → deliverable in a single statement so DuckDB's
# planner can optimise. The DISTINCT is load-bearing: a single event
# can be cited by multiple deliverables; we don't want to overcount.
_DEEP_JOIN_SQL = """
WITH source_event_rows AS (
    -- Explode the JSON-encoded source_event_ids array into rows.
    -- DuckDB's json_each emits one row per array element. The
    -- ``j.value`` column carries the event_id as a JSON-quoted string
    -- (e.g. ``"evt-1"`` not ``evt-1``); TRIM strips the surrounding
    -- double-quotes so the join compares against the bare event_id.
    SELECT
        nb.notebook_id,
        TRIM(BOTH chr(34) FROM CAST(j.value AS TEXT)) AS source_event_id
    FROM per_doc_notebook_blocks nb,
         json_each(nb.source_event_ids) AS j
),
event_to_published AS (
    SELECT DISTINCT b.event_id
    FROM behavior_events b
    JOIN source_event_rows ser ON ser.source_event_id = b.event_id
    JOIN deliverable_citations dc ON dc.notebook_id = ser.notebook_id
    JOIN deliverables d ON d.deliverable_id = dc.deliverable_id
    WHERE d.published_at IS NOT NULL
)
UPDATE behavior_events
SET reward_proxy_deep = 1.0
WHERE event_id IN (SELECT event_id FROM event_to_published)
  AND (reward_proxy_deep IS NULL OR reward_proxy_deep = 0.0)
"""


def run_reward_deep_backfill(
    *,
    db_path: Optional[str] = None,
) -> DeepBackfillResult:
    """Single pass; idempotent. Skips deferred when dependencies are
    absent so the cron caller logs cleanly.

    Returns ``status='ran'`` even when zero rows were updated — that
    means "the join succeeded and no new deep-rewards were found",
    which is the steady-state. ``rows_updated > 0`` only on first
    arrival of a new published deliverable.
    """
    path = db_path or default_db_path()
    present = _tables_present(path, REQUIRED_TABLES)
    missing = tuple(t for t in REQUIRED_TABLES if t not in present)
    if missing:
        return DeepBackfillResult(
            status="deferred",
            reason=(
                f"deep reward backfill deferred: required tables "
                f"missing: {missing}. Apply substrate/notebooks "
                f"migrations to land the deliverables substrate."
            ),
        )

    con = duckdb.connect(path)
    try:
        cur = con.execute(_DEEP_JOIN_SQL)
        rows_updated = cur.fetchone()
        # DuckDB UPDATE returns rowcount via .fetchone() on some
        # versions; on others it's None. Probe both shapes.
        if rows_updated is not None and isinstance(rows_updated, tuple):
            n = int(rows_updated[0]) if rows_updated and rows_updated[0] is not None else 0
        else:
            # Fall back to counting after the fact.
            n = int(con.execute(
                "SELECT COUNT(*) FROM behavior_events "
                "WHERE reward_proxy_deep = 1.0"
            ).fetchone()[0])
    finally:
        con.close()

    return DeepBackfillResult(
        status="ran",
        reason=(
            f"reward_deep backfill complete; {n} row(s) now carry "
            f"reward_proxy_deep=1.0. Re-runs are no-ops until a new "
            f"deliverable is published."
        ),
        rows_updated=n,
    )


__all__ = ["DeepBackfillResult", "run_reward_deep_backfill"]
