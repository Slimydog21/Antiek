"""
Cross-process arXiv request throttle.

Root cause this closes (regression fixture
``tests/regression/agent_failures/arxiv-429-export-ban.yaml``): Antiek's
throttle was *in-process only*. A second shell — or the §7 daemon's
next cycle running in its own process — had no knowledge of the first
process's request history, so the two together exceeded arXiv's
published limit (1 query / 3s) and tripped the IP-scoped 429 limiter.
The ban sentinel (``ban_state``) stops a *known* ban from being
re-triggered; this throttle stops the ban from *happening* in the first
place by spacing requests across every process that shares the host.

The mechanism is the smallest thing that's actually correct under
multiple processes: a single lock file serializes a read-modify-write of
a shared "last request timestamp" file. While one process holds the
lock, it (a) reads the last request time, (b) sleeps just long enough to
honor the minimum interval, (c) stamps the new time, then (d) releases.
Holding the lock across the sleep is deliberate — it both serializes
*and* spaces requests, which is exactly rate-limiter semantics. A design
that released the lock before sleeping would let N processes all read
the same "last time," all compute the same short sleep, and all fire at
once — the thundering-herd bug that an in-process lock can't see.

Why wall-clock (``time.time()``) not ``monotonic()``: the timestamp must
be comparable *across processes* and survive a process restart. Monotonic
clocks are per-process and reset on reboot. Wall-clock is the right tool
here despite its usual hazards, because the only operation is "has at
least N seconds elapsed since a timestamp another process wrote" — a
duration comparison that a backward clock step makes *more* conservative
(longer waits), never less safe.

State lives under ``~/.antiek/`` so every Antiek process shares it:
- ``~/.antiek/arxiv_throttle.lock``  — the flock target (never read)
- ``~/.antiek/arxiv_throttle.state`` — the last-request timestamp

Override the directory via ``ANTIEK_ARXIV_THROTTLE_DIR`` (tests do this
to isolate). Override the interval via ``ANTIEK_ARXIV_MIN_INTERVAL_S``.
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

# arXiv's published guidance: no more than one request every 3 seconds.
# We default slightly above that (3.0) — the limiter measures from the
# server side and network jitter can compress the observed interval, so
# pacing exactly at the limit occasionally trips it. 3.0s is the
# documented floor; callers wanting headroom set the env var higher.
DEFAULT_MIN_INTERVAL_S = 3.0

# Acquiring the throttle should never hang forever — if a crashed
# process left the lock held (it won't, flock releases on fd close /
# process death, but defense in depth), time out and proceed rather
# than wedge ingestion. The timeout is generous relative to the
# interval so it only fires on genuine deadlock.
_LOCK_ACQUIRE_TIMEOUT_S = 30.0
_LOCK_POLL_INTERVAL_S = 0.05


@dataclass(frozen=True)
class ThrottleResult:
    """What ``acquire`` did, for logging / assertions in tests."""

    waited_s: float          # how long we slept to honor the interval
    last_request_at: float   # wall-clock stamp we wrote (epoch seconds)


def _throttle_dir() -> Path:
    override = os.environ.get("ANTIEK_ARXIV_THROTTLE_DIR")
    base = Path(override).expanduser() if override else (Path.home() / ".antiek")
    return base


def _min_interval() -> float:
    raw = os.environ.get("ANTIEK_ARXIV_MIN_INTERVAL_S")
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            return DEFAULT_MIN_INTERVAL_S
    return DEFAULT_MIN_INTERVAL_S


def _lock_path() -> Path:
    return _throttle_dir() / "arxiv_throttle.lock"


def _state_path() -> Path:
    return _throttle_dir() / "arxiv_throttle.state"


@contextmanager
def _flock(lock_path: Path, *, timeout_s: float) -> Iterator[None]:
    """Acquire an exclusive advisory flock with a bounded wait.

    Polls ``LOCK_NB`` rather than blocking forever so a wedged holder
    can't park ingestion indefinitely. Releases on context exit (and
    the kernel releases on process death regardless).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.time() + timeout_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.time() >= deadline:
                    # Timed out waiting. Proceed WITHOUT the lock rather
                    # than wedge — a missed spacing is a smaller harm
                    # than a frozen ingest pipeline. The caller still
                    # honors the ban sentinel separately.
                    break
                time.sleep(_LOCK_POLL_INTERVAL_S)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _read_last_request(state_path: Path) -> float:
    """Last-request epoch seconds, or 0.0 if no prior request / corrupt."""
    try:
        text = state_path.read_text(encoding="utf-8").strip()
        return float(text) if text else 0.0
    except (FileNotFoundError, ValueError, OSError):
        return 0.0


def _write_last_request(state_path: Path, when: float) -> None:
    """Atomically stamp the last-request time. Called under the flock."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".state.tmp")
    tmp.write_text(f"{when:.6f}", encoding="utf-8")
    os.replace(tmp, state_path)


def acquire(
    *,
    min_interval_s: Optional[float] = None,
    now_fn=time.time,
    sleep_fn=time.sleep,
) -> ThrottleResult:
    """Block until it's safe to issue an arXiv request, then stamp.

    Serializes across processes via the lock file and spaces requests by
    at least ``min_interval_s``. ``now_fn`` / ``sleep_fn`` are injectable
    for deterministic tests (real callers use the wall clock + real
    sleep).

    Returns a ``ThrottleResult`` recording how long we waited and the
    timestamp written — useful for asserting spacing in tests and for
    log lines ("throttled arXiv request 1.8s").
    """
    interval = _min_interval() if min_interval_s is None else max(0.0, min_interval_s)
    state_path = _state_path()
    waited = 0.0
    with _flock(_lock_path(), timeout_s=_LOCK_ACQUIRE_TIMEOUT_S):
        last = _read_last_request(state_path)
        now = now_fn()
        elapsed = now - last
        if last > 0.0 and elapsed < interval:
            waited = interval - elapsed
            sleep_fn(waited)
            now = now_fn()
        _write_last_request(state_path, now)
        return ThrottleResult(waited_s=waited, last_request_at=now)


def reset(*, path: Optional[Path] = None) -> None:
    """Clear the throttle state (tests / operator override)."""
    p = path or _state_path()
    if p.exists():
        p.unlink()
