"""Daily Browserbase-spend budget enforcement.

Per spec `docs/integration_exa_browserbase.md` §7.7: a daily cap of
$5 of Browserbase spend (configurable via
`BROWSERBASE_DAILY_BUDGET_USD`) hard-stops new escalation fetches.
No silent fallback; the caller must handle
`BrowserbaseBudgetExceeded`.

Structurally identical to `acquisition/search/exa/budget.py` — same
sidecar-file pattern under `~/.antiek/budgets/`, same single-writer
posture, same UTC-midnight roll. Kept as a sibling file rather than
a generalized "budget" module because the per-call cost shape
differs (Exa charges per result × per call; Browserbase charges
per session-minute) and lifting a shared abstraction would obscure
the asymmetry.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_DAILY_BUDGET_USD: float = 5.0


# Local import of the common base class — lives in `client_browserbase`
# alongside the other Browserbase-side errors. Importing here keeps the
# budget module's `BrowserbaseBudgetExceeded` discoverable via
# `except BrowserbaseProviderError` per Exa-spec §14.4.
from .client_browserbase import BrowserbaseProviderError  # noqa: E402


class BrowserbaseBudgetExceeded(BrowserbaseProviderError):
    """Raised when a `fetch_via_browserbase(...)` would push today's
    Browserbase spend past `BROWSERBASE_DAILY_BUDGET_USD`. Per spec
    §7.7 there is NO silent fallback. The operator either waits or
    raises the cap."""


def _utc_date_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _budget_dir() -> Path:
    base = os.environ.get("ANTIEK_HOME")
    if base:
        p = Path(base) / "budgets"
    else:
        p = Path.home() / ".antiek" / "budgets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _budget_path(date_stamp: Optional[str] = None) -> Path:
    return _budget_dir() / f"browserbase_{date_stamp or _utc_date_stamp()}.json"


def _resolve_cap_usd(cap_override: Optional[float]) -> float:
    if cap_override is not None:
        return float(cap_override)
    v = os.environ.get("BROWSERBASE_DAILY_BUDGET_USD")
    if v:
        try:
            parsed = float(v)
            if parsed < 0:
                raise ValueError("negative")
            return parsed
        except ValueError:
            pass
    return DEFAULT_DAILY_BUDGET_USD


@dataclass
class BudgetState:
    """Snapshot of one day's Browserbase spend."""

    date_stamp: str
    spent_usd: float
    session_count: int
    cap_usd: float


def read_state(date_stamp: Optional[str] = None) -> BudgetState:
    p = _budget_path(date_stamp)
    if not p.exists():
        return BudgetState(
            date_stamp=date_stamp or _utc_date_stamp(),
            spent_usd=0.0,
            session_count=0,
            cap_usd=_resolve_cap_usd(None),
        )
    raw = json.loads(p.read_text())
    return BudgetState(
        date_stamp=raw["date_stamp"],
        spent_usd=float(raw.get("spent_usd", 0.0)),
        session_count=int(raw.get("session_count", 0)),
        cap_usd=float(raw.get("cap_usd", _resolve_cap_usd(None))),
    )


def write_state(state: BudgetState) -> None:
    p = _budget_path(state.date_stamp)
    p.write_text(
        json.dumps(
            {
                "date_stamp": state.date_stamp,
                "spent_usd": state.spent_usd,
                "session_count": state.session_count,
                "cap_usd": state.cap_usd,
            },
            indent=2,
        )
    )


def check_and_reserve(
    cost_estimate_usd: float,
    *,
    cap_override: Optional[float] = None,
    skip_combined_cap: bool = False,
) -> BudgetState:
    """Pre-session check. Raises `BrowserbaseBudgetExceeded` if the
    per-provider cap would be exceeded, or
    `DailyAcquisitionBudgetExceeded` if the combined acquisition
    cap (spec §13.2) would be exceeded. The combined cap fires
    first.

    Browserbase per-session cost is harder to estimate up-front
    than Exa (Exa is per-call; Browserbase is per-minute and the
    operator doesn't know session length in advance). The
    reservation uses a conservative default (`$0.30` per session)
    that callers can override when they know the wait_for shape
    will cap session length lower.
    """
    if not skip_combined_cap:
        from acquisition.search import assert_total_budget_ok  # noqa: PLC0415
        assert_total_budget_ok(cost_estimate_usd)

    cap_usd = _resolve_cap_usd(cap_override)
    state = read_state()
    state.cap_usd = cap_usd
    next_spent = state.spent_usd + cost_estimate_usd
    if next_spent > cap_usd:
        raise BrowserbaseBudgetExceeded(
            f"Browserbase daily budget exceeded: would spend "
            f"${next_spent:.4f} on top of ${state.spent_usd:.4f} "
            f"(cap=${cap_usd:.2f}). Wait until UTC midnight or raise "
            "BROWSERBASE_DAILY_BUDGET_USD."
        )
    state.spent_usd = next_spent
    state.session_count += 1
    write_state(state)
    return state


def record_actual(diff_usd: float) -> BudgetState:
    """Adjust today's spend by `diff_usd` (signed) after a session
    completes and the actual cost is known."""
    state = read_state()
    state.spent_usd = max(0.0, state.spent_usd + diff_usd)
    write_state(state)
    return state
