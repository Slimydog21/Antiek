"""Map a write-lock wait timeout to an honest, retryable HTTP 503.

The substrate is a single-writer DuckDB file (``runtime/db_lock``). A request
that cannot take the write lock inside its interactive budget is a transient
capacity condition, not a server error: the caller should back off and retry
after the current writer (an ingest, a bulk sync) releases the lock.
"""

from __future__ import annotations

from fastapi import HTTPException

from runtime.db_lock import WriteLockTimeout

DEFAULT_RETRY_AFTER_S = 30


def write_lock_busy(
    exc: WriteLockTimeout, *, retry_after_s: int = DEFAULT_RETRY_AFTER_S
) -> HTTPException:
    """Build the 503 for ``exc``; callers ``raise write_lock_busy(exc) from exc``."""
    return HTTPException(
        status_code=503,
        detail="substrate write lock is busy; retry shortly",
        headers={"Retry-After": str(int(retry_after_s))},
    )


__all__ = ["DEFAULT_RETRY_AFTER_S", "write_lock_busy"]
