"""
Cross-process arXiv ban sentinel.

Root cause this closes (regression fixture
``tests/regression/agent_failures/banned-until-sentinel-absent.yaml`` —
the LOAD-BEARING fix in the arxiv-ingestion failure cluster): when
``export.arxiv.org`` returns 429, the ban is IP-scoped and lasts hours.
Antiek's throttle was in-process only, so a second shell (or the §7
daemon's next cycle) re-hit the endpoint during the ban window and
extended it. Without a *shared, persistent* "banned until T" sentinel,
a transient rate limit becomes a self-perpetuating outage.

This module is that sentinel. It lives in a single file under
``~/.antiek/`` so every process — the on-demand worker, the daemon, a
second shell — consults the same state before issuing a request.

Contract:

- ``is_banned()`` — True iff the current time is before the persisted
  ban expiry. Tolerant of a missing/corrupt sentinel (treats as
  not-banned — fail-open on read, because a corrupt sentinel must not
  permanently wedge ingestion).
- ``mark_banned(until)`` — persist the ban expiry. Atomic
  (write-temp-then-rename) so a reader never sees a half-written file.
- ``banned_until()`` — the raw expiry (``datetime | None``) for callers
  that want to log "banned for N more minutes."
- ``clear()`` — remove the sentinel (operator override / test cleanup).

Why fail-OPEN on read but the ban itself is fail-CLOSED: a corrupt
sentinel file should not block ingestion forever (that would turn a
disk hiccup into an outage). But a *valid* ban must be honored —
``is_banned()`` returns True and the caller routes to the PDF endpoint
or Semantic Scholar fallback instead of re-hitting the banned endpoint.

This is the smallest mechanism that actually breaks the
re-trigger loop. A fancier design (exponential backoff state machine,
per-endpoint ban tracking) is deferred until there's evidence the
single-sentinel model is insufficient — per the spec's "smallest
mechanism that prevents the failure" discipline.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DEFAULT_SENTINEL = Path.home() / ".antiek" / "arxiv_banned_until.json"

# arXiv 429 bans are observed to last on the order of hours but the
# exact window is undocumented. A conservative default cooldown that
# the caller can override per mark_banned. The value is justified, not
# pulled from the air: arXiv's published rate guidance is 1 req / 3s;
# an IP that trips the limiter is typically released within a few hours.
# 3h gives margin without parking ingestion for a full day on a
# transient trip.
DEFAULT_COOLDOWN = timedelta(hours=3)


def sentinel_path() -> Path:
    """Resolve the sentinel path, honoring ``ANTIEK_ARXIV_BAN_SENTINEL``."""
    override = os.environ.get("ANTIEK_ARXIV_BAN_SENTINEL")
    if override:
        return Path(override).expanduser()
    return DEFAULT_SENTINEL


def _now() -> datetime:
    return datetime.now(timezone.utc)


def banned_until(*, path: Optional[Path] = None) -> Optional[datetime]:
    """Return the persisted ban-expiry timestamp, or None.

    Fail-open: a missing or corrupt sentinel returns None (not banned).
    A corrupt sentinel must not permanently wedge ingestion.
    """
    p = path or sentinel_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("banned_until")
        if not isinstance(raw, str):
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def is_banned(*, path: Optional[Path] = None, now: Optional[datetime] = None) -> bool:
    """True iff ``now`` (default: wall clock) is before the ban expiry."""
    expiry = banned_until(path=path)
    if expiry is None:
        return False
    current = now or _now()
    return current < expiry


def mark_banned(
    until: Optional[datetime] = None,
    *,
    reason: str = "",
    path: Optional[Path] = None,
    cooldown: timedelta = DEFAULT_COOLDOWN,
) -> datetime:
    """Persist a ban expiry. Atomic write. Returns the expiry set.

    ``until`` defaults to ``now + cooldown``. We never *shorten* an
    existing ban: if a longer ban is already persisted, the existing
    expiry wins (a second 429 within a window shouldn't reset the clock
    earlier than the first observation implied). We DO extend if the
    new expiry is later.
    """
    p = path or sentinel_path()
    new_expiry = until or (_now() + cooldown)

    existing = banned_until(path=p)
    if existing is not None and existing >= new_expiry:
        # Already banned at least this long; keep the longer ban.
        return existing

    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "banned_until": new_expiry.isoformat().replace("+00:00", "Z"),
        "marked_at": _now().isoformat().replace("+00:00", "Z"),
        "reason": reason,
    }
    # Atomic write: temp file in the same dir, then rename. A concurrent
    # reader sees either the old file or the fully-written new one,
    # never a torn write.
    fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), prefix=".arxiv_ban_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_name, p)
    except BaseException:
        # Clean up the temp file on any failure so we don't litter.
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return new_expiry


def clear(*, path: Optional[Path] = None) -> None:
    """Remove the sentinel (operator override / test cleanup). No-op if absent."""
    p = path or sentinel_path()
    if p.exists():
        p.unlink()


def remaining(*, path: Optional[Path] = None, now: Optional[datetime] = None) -> Optional[timedelta]:
    """Time left on the ban, or None if not banned. For log messages."""
    expiry = banned_until(path=path)
    if expiry is None:
        return None
    current = now or _now()
    delta = expiry - current
    return delta if delta.total_seconds() > 0 else None
