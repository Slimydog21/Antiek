"""Rolling write-path refusal telemetry for ``POST /api/ad/frame-telemetry``.

Prod incident 2026-10-02/03 (measured in
``.audit/2026-10-01-anatomy/GRADE-2026-10-01.md`` and
``INDEPENDENT-GRADE.md``): the restarted ``arxiv_oai_sync --bulk`` held the
DuckDB write lock at ~97% duty, and the route refused
**28,562 of 33,776 flushes = 84.6%** with 503 ``ad_frame_writer_busy`` for
~28 hours while ``/health`` reported ``{"status":"ok"}`` the whole time and
the 5-minute ``antiek-health-probe`` unit stayed green — every existing
health signal measured *liveness* (does the process answer), none measured
the *write path* (can a write land).

This module is the missing signal: an in-memory, thread-safe rolling window
of frame-telemetry write attempts and their outcomes. It is deliberately

- **in-memory** — it never opens a DuckDB handle, so it adds zero contention
  to the resource it measures and can never become a second writer;
- **route-local** — the route records each outcome; ``/health`` only reads a
  snapshot, so the read stays O(window) and never blocks on the lock;
- **rate-based, not count-based** — some refusal is CORRECT behaviour (the
  sync legitimately holds the lock; ``Retry-After: 1`` lets the emitter
  re-send the idempotent batch). Only a sustained refusal *rate* is
  pathological.

Threshold derivation (measured anchors, not round numbers):

- healthy, post-fix production, sync running: **2 of 65 flushes refused =
  3.1%** (4-minute window, 2026-10-02, recorded at the incident resolution);
- tolerated degradation, 2026-10-01 (sync at full duty, pre-fix):
  **19.4% of flushes not served over 24h** — the highest refusal level the
  operator ever reviewed and accepted as "correct remaining behaviour";
- the incident: **84.6% sustained for 28h**, with 1,000-1,700 refusals in
  EVERY hour (hourly histogram measured, not sampled).

``FRAME_WRITE_ALERT_THRESHOLD = 0.25`` sits ~8x above the measured healthy
rate, above the highest-ever-tolerated 19.4%, and at less than a third of
the measured incident rate — so it cannot cry wolf on the healthy shape and
cannot stay silent on the incident shape.

``FRAME_WRITE_MIN_ATTEMPTS = 30`` derives from measured traffic: ~240-425
flushes per 15 minutes in both healthy and incident windows, so 30 only
suppresses alerting when traffic has essentially stopped — a state in which
a refusal rate is unmeasurable anyway.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

# 15 minutes — matches the probe's provider-ratio window so one probe read
# sees a settled window, and long enough that the sync's legitimate short
# lock holds (seconds) cannot trip it.
FRAME_WRITE_WINDOW_S = 900.0
# Derived above: 8x the measured healthy rate (3.1%), above the highest
# tolerated degradation (19.4%), a third of the incident rate (84.6%).
FRAME_WRITE_ALERT_THRESHOLD = 0.25
# ~8x below the quietest measured 15-minute traffic (~240 flushes).
FRAME_WRITE_MIN_ATTEMPTS = 30


@dataclass(frozen=True)
class FrameWriteSnapshot:
    window_seconds: int
    attempts: int
    refused: int
    refusal_rate: float | None  # None when no attempts in window
    alert_threshold: float
    min_attempts: int
    alert_recommended: bool
    alert_reason: str | None


class FrameWriteHealth:
    """Thread-safe rolling-window counter. The accrual runs in
    ``asyncio.to_thread``, so recording must be safe off the event loop."""

    def __init__(
        self,
        *,
        window_s: float = FRAME_WRITE_WINDOW_S,
        alert_threshold: float = FRAME_WRITE_ALERT_THRESHOLD,
        min_attempts: int = FRAME_WRITE_MIN_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_s = window_s
        self._alert_threshold = alert_threshold
        self._min_attempts = min_attempts
        self._clock = clock
        self._events: deque[tuple[float, bool]] = deque()
        self._lock = threading.Lock()

    def record(self, *, refused: bool) -> None:
        """Record one write-path attempt outcome. An attempt is any request
        that reached the accrual step; ``refused=True`` means it left as a
        retryable 503 (write-lock timeout or write configuration conflict)."""
        now = self._clock()
        with self._lock:
            self._events.append((now, refused))
            self._prune(now)

    def snapshot(self) -> FrameWriteSnapshot:
        now = self._clock()
        with self._lock:
            self._prune(now)
            attempts = len(self._events)
            refused = sum(1 for _, r in self._events if r)
        rate = (refused / attempts) if attempts else None
        alert = rate is not None and attempts >= self._min_attempts and rate > self._alert_threshold
        reason = (
            (
                f"frame-telemetry refused {refused}/{attempts} writes "
                f"({rate:.1%}) in the last {int(self._window_s)}s "
                f"(threshold {self._alert_threshold:.0%})"
            )
            if alert
            else None
        )
        return FrameWriteSnapshot(
            window_seconds=int(self._window_s),
            attempts=attempts,
            refused=refused,
            refusal_rate=rate,
            alert_threshold=self._alert_threshold,
            min_attempts=self._min_attempts,
            alert_recommended=alert,
            alert_reason=reason,
        )

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_s
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()


# Module-level default, used when a route is mounted outside ``create_app``
# (unit tests) and no per-app instance is available on ``app.state``.
_default = FrameWriteHealth()


def frame_write_health_for(app: object) -> FrameWriteHealth:
    """Resolve the per-app recorder, falling back to the module default."""
    state = getattr(app, "state", None)
    inst = getattr(state, "frame_write_health", None) if state is not None else None
    return inst if isinstance(inst, FrameWriteHealth) else _default
