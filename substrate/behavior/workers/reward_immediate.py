"""Immediate-horizon reward proxy backfill worker (SPR-01 M5).

Real implementation. Reads only ``behavior_events`` — no notebooks
or deliverables joins. Safe to run on a 1-minute cron from
day one.

Contract: for each ``cross_doc_link_surfaced`` row with
``reward_proxy_immediate IS NULL``, look in the same ``session_id``
for a follow-up ``cross_doc_link_clicked`` or
``cross_doc_link_dismissed`` with the matching ``link_id`` (state
side of the click event) within ``IMMEDIATE_WINDOW_S`` seconds.

Mapping (binary today):
- A click within window → 1.0
- A dismiss or no follow-up within window → 0.0

See ``substrate/behavior/REWARD_PROXY.md`` §"Worker 1" for the
canonical join query.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

import duckdb

try:
    from ...runtime.db_lock import connect_write
    from ..schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Open a non-read-only connection for a SELECT path. See
    substrate.behavior.consent._connect_for_read for the rationale —
    DuckDB does not permit mixing read-only and read-write
    connections within a single process."""
    return duckdb.connect(db_path)


IMMEDIATE_WINDOW_S: int = 5
"""Seconds within which a click on a surfaced link is considered
immediate. 5s mirrors the master spec sprint card. Bumping this
requires re-running the worker over historical rows (the worker
is idempotent on NULL rows, so re-running just re-fills, but a
larger window may also flip rows from 0.0 → 1.0 — bump with care)."""


@dataclass(frozen=True)
class ImmediateBackfillResult:
    """Diagnostic returned by ``run_reward_immediate_backfill``.

    Tests use this to assert worker behaviour without poking at the
    DB directly.
    """

    surfaced_inspected: int
    rows_set_positive: int
    rows_set_negative: int

    @property
    def rows_updated(self) -> int:
        return self.rows_set_positive + self.rows_set_negative


def run_reward_immediate_backfill(
    *,
    db_path: Optional[str] = None,
    window_s: int = IMMEDIATE_WINDOW_S,
) -> ImmediateBackfillResult:
    """Single pass over rows with ``reward_proxy_immediate IS NULL``.

    Idempotent: rows already filled are skipped. Safe to re-run on
    a cron.
    """
    path = db_path or default_db_path()

    # 1. Pull candidate surfaced rows. We carry session_id + link_id +
    #    timestamp_utc for the in-Python join (the SQL JSON-extract path
    #    is in the docstring; doing the join in Python here keeps the
    #    worker portable across DuckDB versions whose JSON extract
    #    syntaxes vary).
    con_r = _connect_for_read(path)
    try:
        surfaced = con_r.execute(
            "SELECT event_id, session_id, action, timestamp_utc "
            "FROM behavior_events "
            "WHERE event_type = 'cross_doc_link_surfaced' "
            "  AND reward_proxy_immediate IS NULL"
        ).fetchall()

        # Pull all follow-ups for the same sessions. We restrict to
        # sessions that have at least one surfaced-pending row.
        sessions = sorted({s[1] for s in surfaced})
        if not sessions:
            return ImmediateBackfillResult(0, 0, 0)
        placeholders = ",".join("?" * len(sessions))
        follow_ups = con_r.execute(
            f"SELECT session_id, event_type, state, timestamp_utc "
            f"FROM behavior_events "
            f"WHERE session_id IN ({placeholders}) "
            f"  AND event_type IN ('cross_doc_link_clicked', "
            f"                     'cross_doc_link_dismissed')",
            sessions,
        ).fetchall()
    finally:
        con_r.close()

    # 2. Index follow-ups by (session_id, link_id) → list of (kind, ts).
    by_link: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for sess, kind, state_json, ts in follow_ups:
        try:
            state = json.loads(state_json) if isinstance(state_json, str) else state_json
            link_id = state.get("link_id") if isinstance(state, dict) else None
        except Exception:
            link_id = None
        if not link_id:
            continue
        key = (sess, link_id)
        # ``ts`` is a datetime; convert to unix seconds for the window math.
        try:
            ts_s = ts.timestamp()
        except AttributeError:
            from datetime import datetime
            ts_s = datetime.fromisoformat(str(ts)).timestamp()
        by_link.setdefault(key, []).append((kind, ts_s))

    # 3. For each surfaced row, find the first follow-up in window.
    positives: list[str] = []
    negatives: list[str] = []
    for event_id, sess, action_json, surfaced_ts in surfaced:
        try:
            action = json.loads(action_json) if isinstance(action_json, str) else action_json
            link_id = action.get("link_id") if isinstance(action, dict) else None
        except Exception:
            link_id = None
        if not link_id:
            # Malformed row — set to negative so the worker doesn't
            # keep retrying. The breadcrumb on stderr lets ops notice.
            sys.stderr.write(
                f"reward_immediate: surfaced row {event_id} missing "
                f"action.link_id; marking as 0.0\n"
            )
            negatives.append(event_id)
            continue

        try:
            surfaced_ts_s = surfaced_ts.timestamp()
        except AttributeError:
            from datetime import datetime
            surfaced_ts_s = datetime.fromisoformat(str(surfaced_ts)).timestamp()

        candidates = by_link.get((sess, link_id), [])
        in_window = [
            (kind, t)
            for kind, t in candidates
            if 0.0 <= (t - surfaced_ts_s) <= window_s
        ]
        if in_window:
            # First-in-window. If it's a click → positive. A dismiss
            # in window → still negative (explicit dismissal is a
            # negative signal). Tie-broken by timestamp.
            in_window.sort(key=lambda kt: kt[1])
            first_kind = in_window[0][0]
            if first_kind == "cross_doc_link_clicked":
                positives.append(event_id)
            else:
                negatives.append(event_id)
        else:
            negatives.append(event_id)

    if not positives and not negatives:
        return ImmediateBackfillResult(len(surfaced), 0, 0)

    # 4. Write back. One transaction.
    con_w = connect_write(path, purpose="reward_immediate_backfill")
    try:
        for ids, value in ((positives, 1.0), (negatives, 0.0)):
            if not ids:
                continue
            CHUNK = 200
            for i in range(0, len(ids), CHUNK):
                chunk = ids[i : i + CHUNK]
                placeholders2 = ",".join("?" * len(chunk))
                con_w.execute(
                    f"UPDATE behavior_events "
                    f"SET reward_proxy_immediate = ? "
                    f"WHERE event_id IN ({placeholders2})",
                    [value, *chunk],
                )
    finally:
        con_w.close()

    return ImmediateBackfillResult(
        surfaced_inspected=len(surfaced),
        rows_set_positive=len(positives),
        rows_set_negative=len(negatives),
    )


__all__ = [
    "IMMEDIATE_WINDOW_S",
    "ImmediateBackfillResult",
    "run_reward_immediate_backfill",
]
