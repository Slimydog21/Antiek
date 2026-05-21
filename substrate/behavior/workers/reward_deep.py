"""Deep-horizon reward proxy backfill worker (SPR-01 M5).

STUB. The deep signal requires a ``deliverables`` table (Sprint 17+
creation surface) that does not exist today. See
``substrate/behavior/REWARD_PROXY.md`` §"Worker 3" for the
canonical join.

Same shape as the medium worker: probe for dependency tables, exit
cleanly with a ``deferred`` status if any are missing. The cron
caller can run this from day one without crashing.
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


REQUIRED_TABLES: tuple[str, ...] = (
    "notebooks",
    "notebook_blocks",
    "deliverables",
    "deliverable_citations",
)
"""Tables this worker joins against. The first two are SPR-08
artifacts; the last two are Sprint 17+. All missing today; this
stub exits cleanly until they land."""


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


def run_reward_deep_backfill(
    *,
    db_path: Optional[str] = None,
) -> DeepBackfillResult:
    """Single pass; stub until Sprint 17+ lands a deliverables table.

    Returns ``status='deferred'`` when dependencies are absent so
    the cron caller can log + move on without raising.
    """
    path = db_path or default_db_path()
    present = _tables_present(path, REQUIRED_TABLES)
    missing = tuple(t for t in REQUIRED_TABLES if t not in present)
    if missing:
        return DeepBackfillResult(
            status="deferred",
            reason=(
                f"deep reward backfill deferred: required tables "
                f"missing: {missing}. Sprint 17+ will create "
                f"deliverables; this is expected at SPR-01 closeout."
            ),
        )

    return DeepBackfillResult(
        status="deferred",
        reason=(
            "stub: real implementation pending. See "
            "substrate/behavior/REWARD_PROXY.md §Worker 3 for the "
            "canonical join query."
        ),
    )


__all__ = ["DeepBackfillResult", "run_reward_deep_backfill"]
