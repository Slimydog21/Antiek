"""Append-only ban-event log: attribute every ban sentinel to who and where.

On 2026-09-20 a real arXiv 429 armed ``~/.antiek/source_throttle.json`` and
nothing on disk recorded which process, URL, or argv drew it. Each ban-status
response must append ONE JSON line naming who and where.

Invariants (hard — do not weaken):

* This is plain append-only JSONL in the state dir. It is NOT a database.
* It touches NO DuckDB path and imports nothing from ``runtime/db_lock`` or
  ``substrate/graph``. It takes no lock.
* Writing the log must NEVER raise into the caller and must never prevent the
  ban sentinel from being armed: callers write the sentinel FIRST, then append
  the event. A failed append is a warning, not a control-flow failure.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

BAN_EVENT_LOG_ENV = "ANTIEK_BAN_EVENT_LOG_PATH"
BAN_EVENT_FIELDS: tuple[str, ...] = ("ts", "source", "status", "host", "pid", "argv0")

_log = logging.getLogger(__name__)


def default_ban_event_log_path() -> str:
    """Resolve the ban-event JSONL path.

    Precedence: ``ANTIEK_BAN_EVENT_LOG_PATH`` (non-empty) >
    ``$ANTIEK_HOME/ban_events.jsonl`` when ``ANTIEK_HOME`` is non-empty after
    ``.strip()`` (``ANTIEK_HOME`` REPLACES ``~/.antiek`` — same convention as
    ``acquisition.arxiv.throttle.default_state_path``) >
    ``~/.antiek/ban_events.jsonl``.
    """
    env = os.environ.get(BAN_EVENT_LOG_ENV)
    if env:
        return env
    home = os.environ.get("ANTIEK_HOME", "").strip()
    if home:
        return str(Path(home) / "ban_events.jsonl")
    return str(Path.home() / ".antiek" / "ban_events.jsonl")


def _host_from_url(url: str | None) -> str:
    """Lower-cased hostname from ``url``, or \"\" when absent/unparseable."""
    if not url:
        return ""
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return ""
    return (host or "").lower()


def _argv0() -> str:
    if sys.argv and sys.argv[0]:
        return sys.argv[0]
    return sys.executable or "?"


def append_ban_event(
    *,
    source: str,
    status: int,
    url: str | None = None,
    ts: float | None = None,
    path: str | None = None,
) -> None:
    """Append ONE six-field JSON line naming who drew the ban.

    Never raises: ``OSError``/``ValueError`` during mkdir or write are logged
    as warnings and swallowed. Callers MUST arm the ban sentinel BEFORE
    calling this so a failed append cannot prevent the sentinel write.
    """
    event: dict[str, object] = {
        "ts": float(time.time() if ts is None else ts),
        "source": source,
        "status": int(status),
        "host": _host_from_url(url),
        "pid": os.getpid(),
        "argv0": _argv0(),
    }
    target = path if path is not None else default_ban_event_log_path()
    try:
        dirname = os.path.dirname(target)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        line = json.dumps(event, sort_keys=True) + "\n"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line)
    except (OSError, ValueError) as exc:
        _log.warning("append_ban_event failed for %s: %s", target, exc)


def read_ban_events(
    path: str | None = None, last: int | None = None
) -> list[dict[str, object]]:
    """Read ban events from ``path`` (default: resolved log path).

    Missing file yields ``[]``. Blank lines, non-JSON lines, and JSON values
    that are not objects are skipped. Returns the last ``last`` events in file
    order (all when ``last`` is None).
    """
    target = path if path is not None else default_ban_event_log_path()
    try:
        raw = Path(target).read_text(encoding="utf-8")
    except OSError:
        return []
    events: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            val = json.loads(line)
        except ValueError:
            continue
        if isinstance(val, dict):
            events.append(val)
    if last is None:
        return events
    if last <= 0:
        return []
    return events[-last:]
