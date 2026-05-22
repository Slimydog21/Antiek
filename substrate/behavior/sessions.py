"""Derived ``last_session_at`` over the behavior store (2026-05-22).

SPR-06 surfaced the gap: the substrate has no ``users.last_session_at``
column, so the post-login routing falls back to a per-device localStorage
proxy that treats the same user on a new browser as "new."

The data already exists in the behavior store. Every interaction emits a
``behavior_events`` row with ``timestamp_utc``. The "last session" for a
user is just::

    SELECT MAX(timestamp_utc) FROM behavior_events WHERE user_id = ?

There is no need for a separate table; the read is O(log n) against the
existing ``(user_id, timestamp_utc)`` index from SPR-01.

This module exposes the derived view as a function the FastAPI auth path
can call. SPR-06's ``postLogin.ts`` resolver can layer on this answer
when the substrate is reachable, falling back to localStorage when it
isn't (the localStorage proxy stays in place; this is a strictly
better-when-available signal).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import duckdb

from substrate.graph import default_db_path


def get_last_session_at(
    user_id: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[datetime]:
    """Return the most recent ``timestamp_utc`` for any behavior event
    owned by ``user_id``, or ``None`` if the user has no events.

    Reads ``behavior_events`` through a read-only DuckDB connection. The
    existing ``(user_id, timestamp_utc)`` index makes this an O(log n)
    point read, not a scan. No memoisation — the call is cheap and the
    cache-invalidation question (event emitted just now → answer must
    reflect it) is the kind of bug that bites silently.
    """
    path = db_path or default_db_path()
    with duckdb.connect(path) as con:
        row = con.execute(
            "SELECT MAX(timestamp_utc) FROM behavior_events WHERE user_id = ?",
            [user_id],
        ).fetchone()
    if row is None or row[0] is None:
        return None
    raw = row[0]
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        # DuckDB normally returns datetime, but normalise just in case.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return None


def is_returning_user(
    user_id: str,
    *,
    threshold_days: int = 1,
    db_path: Optional[str] = None,
) -> bool:
    """True if the user has ANY behavior event older than
    ``threshold_days``. Used by SPR-06's post-login routing as the
    "this user has been here before" gate.

    A user whose first-ever event was 3 seconds ago is mid-onboarding,
    not returning. A user with a 2-day-old event AND a current-session
    event is returning — they came back. The criterion is "has any
    history" not "last activity is old," because mid-session users
    should still be routed as returning (continue where they left
    off).

    SQL form: EXISTS(SELECT 1 FROM behavior_events WHERE user_id=? AND
    timestamp_utc < cutoff). The point read is O(log n) via the
    existing (user_id, timestamp_utc) index.
    """
    path = db_path or default_db_path()
    cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)
    with duckdb.connect(path) as con:
        row = con.execute(
            "SELECT 1 FROM behavior_events "
            "WHERE user_id = ? AND timestamp_utc < ? LIMIT 1",
            [user_id, cutoff],
        ).fetchone()
    return row is not None


__all__ = ["get_last_session_at", "is_returning_user"]
