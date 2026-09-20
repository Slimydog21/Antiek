"""Daily quota-UNIT meter for unit-metered connectors (spec §5.5) — YouTube first.

The second BYO-tools guard, beside the host-global rate governor. Where the
governor spaces requests in time (EDGAR/Reddit windows), the quota meter
counts a vendor's DAILY UNIT budget — YouTube Data API v3 meters every call
in quota units (a ``search.list`` costs 100 units of a 10,000-unit/day
budget), and Google resets the ledger at **midnight America/Los_Angeles**
(PT), not UTC.

It mirrors ``acquisition/search/exa/budget.py`` (``check_and_reserve`` /
``record_actual`` / env-cap shape) with two deltas, both spec-mandated:

  * UNITS not USD — the unit table is data (``YOUTUBE_UNIT_COSTS``), so the
    meter never needs to know what an operation costs; the connector does
    and passes the number;
  * RESET TZ — the day rolls over in the vendor's reset timezone
    (``QuotaMeter(reset_tz=...)``), computed via ``zoneinfo`` on the injected
    clock, not ``datetime.utcnow``.

PERSISTENCE: a date-stamped JSON sidecar ``{state_dir}/{vendor}_quota_{day}.
json`` — the exa-budget pattern verbatim: the date stamp in the FILENAME
rolls the budget (no cron, no state migration), the file is written
atomically (tmp + replace), and the meter does NO DuckDB writes (spec §5.0
single-writer: connector runtime state is a JSON sidecar, never a DB row).

ADVISORY-CONSERVATIVE (spec §10 risk 3, honored here, not papered over): a
client-side counter can undercount Google's real ledger (a crashed process
never records; a multithreaded burst races the file). So the meter is only
ever a REFUSAL threshold, never a permission — and the vendor's own signal
wins: on any 403 ``quotaExceeded`` the connector calls :meth:`mark_exhausted`
to hard-set the meter at 0 remaining until the next PT-day reset, regardless
of the local count. Undercount degrades to one 403 + hard-set, never to an
unmetered spend.

CONCURRENCY: same honesty bar as the exa budget — thread-safe in-process
(``threading.Lock`` around the read-modify-write) and atomic across
processes (tmp+replace). The single-operator box runs one process at a time
(Sprint 22+ moves this into DuckDB with ``db_lock`` — accepted debt, same
as ``budget_ledger.py``'s).

FAIL CLOSED (spec §5.0): ``units <= 0`` is a caller bug (``ValueError``,
mirroring ``budget_ledger.py:620-625``'s "pricing-unknown must map to a
conservative positive cap upstream, never to free"); an unreadable state
file reads as FULL (refuse, never grant); an unresolvable reset timezone
raises rather than silently switching the day — the connector then refuses
instead of spending against a wrong-day budget.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ENV_QUOTA_DIR = "ANTIEK_CONNECTOR_QUOTA_DIR"

# YouTube Data API v3 unit ledger (spec §5.5 — the table is data; a
# connector passes the number for its operation, the meter just counts).
# Source: Google's public cost table for the Data API (fixture-validated,
# live-unverified — re-verify at the vendor portal if a cost changes).
YOUTUBE_UNIT_COSTS: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
}

# Google grants 10,000 units/day by default; the reset is at midnight
# Pacific (America/Los_Angeles) — Google's documented reset, NOT UTC.
YOUTUBE_UNITS_PER_DAY = 10_000
YOUTUBE_RESET_TZ = "America/Los_Angeles"


def default_quota_dir() -> str:
    """The cross-process per-vendor quota state directory.

    Honors ``ANTIEK_CONNECTOR_QUOTA_DIR`` for tests / alternate homes;
    otherwise ``(ANTIEK_HOME|~/.antiek)/connectors/quota/`` — a sibling of
    the rate governor's state dir (``runtime/connectors/rate_governor.py``),
    never in the repo.
    """
    env = os.environ.get(_ENV_QUOTA_DIR)
    if env:
        return env
    home = os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek"))
    return str(Path(home) / "connectors" / "quota")


class QuotaExhausted(RuntimeError):
    """The daily unit budget is (or will be) exhausted for this vendor day.

    Raised by :meth:`QuotaMeter.check_and_reserve` BEFORE any request is
    sent — the connector must NOT send; the caller surfaces ``reset_at`` so
    the user sees exactly when the budget reopens. Carries no key material
    (there is none here) and no request content.
    """

    def __init__(self, vendor: str, units: int, remaining: int, reset_at: str) -> None:
        self.vendor = vendor
        self.units = units
        self.remaining = remaining
        self.reset_at = reset_at
        super().__init__(
            f"{vendor} daily quota exhausted: {units} units requested, "
            f"{remaining} remaining; resets {reset_at}"
        )


@dataclass(frozen=True)
class QuotaSnapshot:
    """One vendor-day's meter state — the shape the meter surface
    (``GET /{connector_id}/meter``, the UI quota bar) renders. ``reset_at``
    is an ISO-8601 datetime WITH the vendor-TZ offset (e.g.
    ``2026-08-08T00:00:00-07:00``), unambiguous across DST."""

    remaining: int
    units_per_day: int
    reset_at: str
    hard_exhausted: bool


@dataclass
class _MeterState:
    """The persisted per-day state. ``used_units`` is the honest counter
    (may briefly exceed the budget; ``remaining`` clamps at 0); a
    ``hard_exhausted`` mark from the vendor's own 403 ``quotaExceeded``
    signal forces remaining to 0 even if the counter disagrees."""

    day: str
    used_units: int
    hard_exhausted: bool

    def remaining(self, units_per_day: int) -> int:
        if self.hard_exhausted:
            return 0
        return max(0, units_per_day - self.used_units)


class QuotaMeter:
    """One vendor's daily quota-unit meter (spec §5.5).

    Construct one per connector (or inject it): ``check_and_reserve(units)``
    before the send (refuses when the day's budget cannot cover it),
    ``record_actual(units)`` after a successful send, ``mark_exhausted()``
    when the vendor answers 403 ``quotaExceeded`` (advisory-conservative
    hard-set), and ``remaining()`` for the meter surface.

    ``clock`` is injectable epoch-seconds (``time.time`` by default) so tests
    roll the PT day with a fake clock instead of sleeping a real second; the
    day + reset time are computed IN THE VENDOR RESET TZ, so a test can also
    pin ``reset_tz="UTC"`` (``zoneinfo``'s always-present built-in) to stay
    tzdata-free — production uses the vendor's real reset tz.
    """

    def __init__(
        self,
        vendor: str,
        *,
        units_per_day: int = YOUTUBE_UNITS_PER_DAY,
        reset_tz: str = YOUTUBE_RESET_TZ,
        state_dir: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not vendor or not vendor.strip():
            raise ValueError("vendor must be a non-empty string")
        if units_per_day < 1:
            raise ValueError("units_per_day must be >= 1")
        if not reset_tz:
            raise ValueError("reset_tz must be a non-empty IANA tz name")
        self._vendor = vendor
        self._units_per_day = int(units_per_day)
        self._reset_tz = reset_tz
        self._clock = clock
        self._lock = threading.Lock()
        try:
            self._zone = ZoneInfo(reset_tz)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"unknown reset timezone {reset_tz!r} (no tzdata for it on this "
                "host) — pass reset_tz=UTC or install tzdata"
            ) from exc
        state_root = Path(state_dir or default_quota_dir())
        self._state_dir = state_root

    @property
    def vendor(self) -> str:
        return self._vendor

    @property
    def units_per_day(self) -> int:
        return self._units_per_day

    # -- time helpers (vendor-TZ day math, all clock-driven) ------------------

    def _now_dt(self) -> datetime:
        """The current instant, localized to the vendor reset TZ."""
        return datetime.fromtimestamp(self._clock(), tz=self._zone)

    def _day_key(self) -> str:
        return self._now_dt().strftime("%Y-%m-%d")

    def _next_reset_iso(self) -> str:
        """The next vendor-TZ midnight as ISO-8601 WITH offset (DST-safe:
        ``replace(hour=0)`` keeps the zone, whose offset the formatter
        renders)."""
        now = self._now_dt()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.isoformat()

    # -- sidecar file I/O (date-stamped filename = day rollover) --------------

    def _state_path(self, day: str | None = None) -> Path:
        return self._state_dir / f"{self._vendor}_quota_{day or self._day_key()}.json"

    def _read_state(self) -> _MeterState:
        try:
            raw = self._state_path().read_text(encoding="utf-8")
        except FileNotFoundError:
            return _MeterState(day=self._day_key(), used_units=0, hard_exhausted=False)
        except OSError:
            # FAIL CLOSED: an unreadable state file must not read as "no
            # usage yet" — treat the day as full so the next check refuses
            # (the connector surfaces the refusal honestly).
            return _MeterState(
                day=self._day_key(), used_units=self._units_per_day, hard_exhausted=True
            )
        try:
            data = json.loads(raw)
            day = str(data.get("day") or self._day_key())
            used = int(data.get("used_units") or 0)
            hard = bool(data.get("hard_exhausted") or False)
            return _MeterState(day=day, used_units=used, hard_exhausted=hard)
        except (json.JSONDecodeError, ValueError, TypeError):
            return _MeterState(
                day=self._day_key(), used_units=self._units_per_day, hard_exhausted=True
            )

    def _write_state(self, state: _MeterState) -> None:
        path = self._state_path(state.day)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        # Atomic: tmp + replace so a crash mid-write can't leave a truncated
        # file that reads as "no usage" (the governor's atomic-write rule).
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "day": state.day,
                    "used_units": state.used_units,
                    "hard_exhausted": state.hard_exhausted,
                }
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # -- the public meter surface ---------------------------------------------

    def check_and_reserve(self, units: int) -> None:
        """Refuse (or record) a spend of ``units`` against today's budget.

        Raises :class:`QuotaExhausted` — carrying the next reset time — when
        today's remaining units cannot cover the request; the connector must
        NOT send in that case (the refusal happens before any HTTP call).
        Otherwise the units are reserved (persisted immediately, so a crash
        between reserve and record over-holds — the conservative direction).
        """
        if units < 1:
            raise ValueError(f"units must be >= 1, got {units}")
        with self._lock:
            state = self._read_state()
            remaining = state.remaining(self._units_per_day)
            if state.hard_exhausted or remaining < units:
                raise QuotaExhausted(
                    self._vendor, units, remaining, self._next_reset_iso()
                )
            state.used_units += units
            self._write_state(state)

    def record_actual(self, diff_units: int) -> None:
        """Reconcile today's counter with the ACTUAL units a call spent —
        the exa budget's signed-``diff_usd`` shape verbatim.

        ``check_and_reserve`` optimistically ADDS the estimate; when the
        actual cost is known, the caller passes a SIGNED correction: a
        negative diff releases an over-hold (a failed send spent nothing),
        a positive diff books a variable-cost overrun, 0 is a legal no-op.
        The counter clamps at 0 (never negative). For deterministic-cost
        operations (YouTube ``search.list`` = 100 exactly) a successful
        send needs no reconcile — the reservation WAS the actual cost.
        """
        with self._lock:
            state = self._read_state()
            state.used_units = max(0, state.used_units + diff_units)
            self._write_state(state)

    def mark_exhausted(self) -> None:
        """Hard-set today's meter to exhausted (advisory-conservative).

        The vendor's own 403 ``quotaExceeded`` is ground truth: regardless
        of what the local counter says, remaining becomes 0 until the next
        vendor-day reset (spec §10 risk 3 — the client-side counter can
        undercount; the vendor's signal wins).
        """
        with self._lock:
            state = self._read_state()
            state.hard_exhausted = True
            self._write_state(state)

    def remaining(self) -> QuotaSnapshot:
        """Today's meter state, as the meter surface renders it."""
        with self._lock:
            state = self._read_state()
            return QuotaSnapshot(
                remaining=state.remaining(self._units_per_day),
                units_per_day=self._units_per_day,
                reset_at=self._next_reset_iso(),
                hard_exhausted=state.hard_exhausted,
            )


__all__ = [
    "QuotaExhausted",
    "QuotaMeter",
    "QuotaSnapshot",
    "YOUTUBE_RESET_TZ",
    "YOUTUBE_UNIT_COSTS",
    "YOUTUBE_UNITS_PER_DAY",
    "default_quota_dir",
]
