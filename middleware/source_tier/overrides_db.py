"""Chunk tier overrides — DB writer (Sprint 10 day 4-5).

Append-only audit log of post-ingestion retiering decisions.
Backtest reads from here to surface "cited chunks that have since
been demoted." The override is asymmetric (LLM downward-only)
already enforced upstream in ``rules.adjust_tier_after_extraction``;
this writer just persists the decision.

The full chunk's effective tier at query time is the maximum
override tier (i.e. lowest reliability — tier 5 is worst), but
this module doesn't compute that — it just records the timeline.
A future ``chunks_effective_tier`` view can fold the override
history into a single number when a consumer needs it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def record_chunk_tier_override(
    con: Any,
    *,
    chunk_id: str,
    original_tier: int,
    override_tier: int,
    reason: str,
    set_by: Optional[str] = None,
    set_at: Optional[datetime] = None,
) -> None:
    """Append one override row. Requires a ``LockedConnection``.

    ``set_at`` defaults to ``now(UTC)``; pass a fixed value for
    backtest replay scenarios where timing matters."""
    try:
        from ...runtime.db_lock import LockedConnection  # type: ignore[import-not-found]
    except ImportError:
        from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "record_chunk_tier_override requires a LockedConnection."
        )
    if not 1 <= int(original_tier) <= 5:
        raise ValueError(
            f"original_tier must be 1..5, got {original_tier}"
        )
    if not 1 <= int(override_tier) <= 5:
        raise ValueError(
            f"override_tier must be 1..5, got {override_tier}"
        )
    ts = set_at or datetime.now(timezone.utc)
    # DuckDB TIMESTAMP is tz-naive; normalize to naive UTC at the
    # boundary so backtest's `valid_until > ?` comparisons match.
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    con.execute(
        "INSERT INTO chunk_tier_overrides "
        "(chunk_id, original_tier, override_tier, reason, set_at, set_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [chunk_id, int(original_tier), int(override_tier), reason, ts, set_by],
    )
