"""Daemon-level budget enforcement per master-spec §7.4.

Three caps:

  - **Per-investigation cap** — defaults to $2.00. Spec §7.4 hard cap.
    Enforced at spawn time; the daemon refuses to spawn an investigation
    whose declared budget exceeds this cap.
  - **Per-day daemon cap** — defaults to $5.00 via the
    ``ANTIEK_DAEMON_HOURLY_BUDGET_USD`` env (despite the env name,
    we treat it as a daily cap to match the spec's "$5/day default"
    language).
  - **Per-topic depth cap** — defaults to 5 levels. Enforced by
    ``research_topic.ResearchTopic.depth_remaining``, NOT here; this
    module only owns the dollar-cap mechanics.

Persistence: like the Exa budget sidecar, daily spend lives in a
``~/.antiek/budgets/daemon_<utc_date>.json`` sidecar so a daemon
restart doesn't reset the spend tally. UTC midnight rolls naturally
by virtue of the date stamp in the filename — no cron, no migration.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


PER_INVESTIGATION_CAP_USD: float = 2.0
DEFAULT_DAILY_CAP_USD: float = 5.0
MAX_TOPIC_DEPTH: int = 5

_ENV_DAILY_CAP = "ANTIEK_DAEMON_HOURLY_BUDGET_USD"
_ENV_HOME = "ANTIEK_HOME"


class DaemonBudgetError(RuntimeError):
    """Raised when a spawn would exceed a budget cap. The spawn loop
    catches this and emits an ``investigation.chase_halted`` event
    instead of crashing the daemon."""


def _utc_date_stamp(now: Optional[datetime] = None) -> str:
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref.strftime("%Y-%m-%d")


def _budget_dir() -> Path:
    base = os.environ.get(_ENV_HOME)
    if base:
        p = Path(base) / "budgets"
    else:
        p = Path.home() / ".antiek" / "budgets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _budget_path(date_stamp: Optional[str] = None) -> Path:
    return _budget_dir() / f"daemon_{date_stamp or _utc_date_stamp()}.json"


def _resolve_daily_cap(override: Optional[float] = None) -> float:
    if override is not None:
        return max(0.0, float(override))
    raw = os.environ.get(_ENV_DAILY_CAP)
    if raw:
        try:
            v = float(raw)
            return max(0.0, v)
        except ValueError:
            pass
    return DEFAULT_DAILY_CAP_USD


@dataclass
class _BudgetSnapshot:
    """Mutable on-disk snapshot. Use ``DaemonBudget`` for the public
    surface; this is the persistence layer only."""

    date_stamp: str
    spent_usd: float
    spawn_count: int
    cap_usd: float


def _read_snapshot(date_stamp: str, cap_usd: float) -> _BudgetSnapshot:
    p = _budget_path(date_stamp)
    if not p.exists():
        return _BudgetSnapshot(
            date_stamp=date_stamp, spent_usd=0.0, spawn_count=0, cap_usd=cap_usd,
        )
    raw = json.loads(p.read_text())
    if not isinstance(raw, dict):
        raise ValueError("budget snapshot must be a JSON object")
    if raw.get("date_stamp") != date_stamp:
        raise ValueError("budget snapshot date does not match its requested UTC day")
    if "spent_usd" not in raw or "spawn_count" not in raw or "cap_usd" not in raw:
        raise ValueError("budget snapshot is missing required accounting fields")
    spent_usd = float(raw["spent_usd"])
    stored_cap_usd = float(raw["cap_usd"])
    spawn_count = raw["spawn_count"]
    if not math.isfinite(spent_usd) or spent_usd < 0:
        raise ValueError("budget snapshot spend must be finite and non-negative")
    if not math.isfinite(stored_cap_usd) or stored_cap_usd < 0:
        raise ValueError("budget snapshot cap must be finite and non-negative")
    if isinstance(spawn_count, bool) or not isinstance(spawn_count, int) or spawn_count < 0:
        raise ValueError("budget snapshot spawn count must be a non-negative integer")
    return _BudgetSnapshot(
        date_stamp=date_stamp,
        spent_usd=spent_usd,
        spawn_count=spawn_count,
        cap_usd=stored_cap_usd,
    )


def _write_snapshot(s: _BudgetSnapshot) -> None:
    p = _budget_path(s.date_stamp)
    p.write_text(
        json.dumps(
            {
                "date_stamp": s.date_stamp,
                "spent_usd": s.spent_usd,
                "spawn_count": s.spawn_count,
                "cap_usd": s.cap_usd,
            },
            indent=2,
        )
    )


@dataclass
class DaemonBudget:
    """Daemon budget enforcement primitive.

    Construct once per daemon process; call ``reserve(...)`` before
    each spawn to atomically check + commit. The reservation is
    optimistic: the caller passes the **expected** cost; if actual
    cost diverges, call ``record_actual(...)`` with the delta.
    """

    daily_cap_usd: float
    per_investigation_cap_usd: float = PER_INVESTIGATION_CAP_USD

    @classmethod
    def from_env(cls) -> "DaemonBudget":
        """Build a budget reading the daily cap from
        ``ANTIEK_DAEMON_HOURLY_BUDGET_USD`` with a $5/day default."""
        return cls(daily_cap_usd=_resolve_daily_cap(None))

    def remaining_today(self, *, now: Optional[datetime] = None) -> float:
        snap = _read_snapshot(_utc_date_stamp(now), self.daily_cap_usd)
        return max(0.0, snap.cap_usd - snap.spent_usd)

    def spent_today(self, *, now: datetime | None = None) -> float:
        """Return recorded spend without folding it through a cap.

        Read models may apply an operator cap that differs from the daemon cap
        stored in the sidecar.  Such callers need the raw spend value so both
        spent and remaining can be computed against the same current cap.
        """
        snap = _read_snapshot(_utc_date_stamp(now), self.daily_cap_usd)
        return snap.spent_usd

    def reserve(
        self,
        expected_cost_usd: float,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        """Atomically check both caps + commit the reservation.

        Raises ``DaemonBudgetError`` if either:
          - ``expected_cost_usd`` > per-investigation cap, OR
          - the daily total would exceed the daily cap.
        """
        if expected_cost_usd < 0:
            raise DaemonBudgetError(
                f"negative expected_cost_usd={expected_cost_usd!r}"
            )
        if expected_cost_usd > self.per_investigation_cap_usd:
            raise DaemonBudgetError(
                f"per-investigation cap exceeded: ${expected_cost_usd:.4f} > "
                f"${self.per_investigation_cap_usd:.2f}"
            )
        date_stamp = _utc_date_stamp(now)
        snap = _read_snapshot(date_stamp, self.daily_cap_usd)
        # The cap on the snapshot may be stale if the operator edited
        # the env between writes; always re-honor the current value.
        snap.cap_usd = self.daily_cap_usd
        if snap.spent_usd + expected_cost_usd > snap.cap_usd:
            raise DaemonBudgetError(
                f"daemon daily cap exceeded: would spend "
                f"${snap.spent_usd + expected_cost_usd:.4f} (cap ${snap.cap_usd:.2f}, "
                f"already spent ${snap.spent_usd:.4f} today)"
            )
        snap.spent_usd += expected_cost_usd
        snap.spawn_count += 1
        _write_snapshot(snap)

    def record_actual(
        self,
        delta_usd: float,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        """Adjust today's spend after a spawn completes. ``delta_usd``
        is signed: a positive value if the investigation cost more
        than reserved, negative if less. The daily total never goes
        below zero."""
        date_stamp = _utc_date_stamp(now)
        snap = _read_snapshot(date_stamp, self.daily_cap_usd)
        snap.cap_usd = self.daily_cap_usd
        snap.spent_usd = max(0.0, snap.spent_usd + delta_usd)
        _write_snapshot(snap)
