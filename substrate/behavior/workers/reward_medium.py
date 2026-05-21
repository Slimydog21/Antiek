"""Medium-horizon reward proxy backfill worker (SPR-01 M5).

STUB. The medium signal requires Tier-2 notebook references — see
``substrate/behavior/REWARD_PROXY.md`` §"Worker 2". The notebooks
table is a SPR-08 artifact; until then this worker is a no-op
that handles the empty-state case cleanly and logs a single
breadcrumb so an ops operator can confirm the cron is firing.

The canonical join query lives in REWARD_PROXY.md. When SPR-08
lands and `notebooks` + `notebook_blocks` populate, swap the no-op
in ``_run_real`` below for that join.
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


REQUIRED_TABLES: tuple[str, ...] = ("notebooks", "notebook_blocks")
"""Tables this worker joins against. Stub-aware: if any are missing
the worker exits with ``status='deferred'`` rather than crashing."""


@dataclass(frozen=True)
class MediumBackfillResult:
    """Diagnostic returned by ``run_reward_medium_backfill``."""

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


def run_reward_medium_backfill(
    *,
    db_path: Optional[str] = None,
) -> MediumBackfillResult:
    """Single pass; stub until SPR-08 lands notebooks emission.

    Returns ``status='deferred'`` when dependencies are absent so
    the cron caller can log + move on without raising.
    """
    path = db_path or default_db_path()
    present = _tables_present(path, REQUIRED_TABLES)
    missing = tuple(t for t in REQUIRED_TABLES if t not in present)
    if missing:
        return MediumBackfillResult(
            status="deferred",
            reason=(
                f"medium reward backfill deferred: required tables "
                f"missing: {missing}. SPR-08 will populate; this is "
                f"expected at SPR-01 closeout."
            ),
        )

    # Tables exist but are empty — also deferred. The canonical join
    # query lives in REWARD_PROXY.md.
    con = _connect_for_read(path)
    try:
        nb_count = con.execute("SELECT COUNT(*) FROM notebooks").fetchone()[0]
    finally:
        con.close()
    if not nb_count:
        return MediumBackfillResult(
            status="empty",
            reason="notebooks present but empty; nothing to backfill",
        )

    # When SPR-08 lands and the canonical join in REWARD_PROXY.md is
    # ready, replace this with the real UPDATE. Today, return a stub
    # diagnostic so the cron caller knows the worker is intact.
    return MediumBackfillResult(
        status="deferred",
        reason=(
            "stub: real implementation pending. See "
            "substrate/behavior/REWARD_PROXY.md §Worker 2 for the "
            "canonical join query."
        ),
    )


__all__ = ["MediumBackfillResult", "run_reward_medium_backfill"]
