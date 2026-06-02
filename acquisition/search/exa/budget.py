"""Daily Exa-spend budget enforcement.

Per spec `docs/integration_exa_browserbase.md` §6.7: a daily cap of
$5 of Exa spend (configurable via `EXA_DAILY_BUDGET_USD`) hard-stops
new calls. No silent fallback to a different provider; the caller
must handle `DiscoveryBudgetExceeded`.

Persistence: a sidecar JSON file under
`~/.antiek/budgets/exa_<utc_date>.json`. UTC midnight rolls the
budget by virtue of the date stamp in the filename — no cron, no
state migration. Old files can be deleted by anyone.

Concurrency: the substrate is single-writer (per architecture_notes
§2.3); the budget is single-writer too. Two concurrent processes
would race; for now this is fine because the operator-driven
substrate runs one process at a time. When multi-user lands (Sprint
22+), the budget moves into DuckDB and inherits `db_lock`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DAILY_BUDGET_USD: float = 5.0


def _utc_date_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _budget_dir() -> Path:
    base = os.environ.get("ANTIEK_HOME")
    if base:
        p = Path(base) / "budgets"
    else:
        p = Path.home() / ".antiek" / "budgets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _budget_path(date_stamp: str | None = None) -> Path:
    return _budget_dir() / f"exa_{date_stamp or _utc_date_stamp()}.json"


def _resolve_cap_usd(cap_override: float | None) -> float:
    if cap_override is not None:
        return float(cap_override)
    v = os.environ.get("EXA_DAILY_BUDGET_USD")
    if v:
        try:
            parsed = float(v)
            if parsed < 0:
                raise ValueError("negative")
            return parsed
        except ValueError:
            # Malformed env var falls back to the default — the operator
            # sees the default-cap behavior in their weekly report and
            # corrects there.
            pass
    return DEFAULT_DAILY_BUDGET_USD


@dataclass
class BudgetState:
    """Snapshot of one day's Exa spend.

    `cap_usd` is the threshold at the moment of last write; it may
    diverge from the env var if the operator edited the env without
    rolling the file. The enforcement function always re-reads the
    env, so the file's cap is informational.
    """

    date_stamp: str
    spent_usd: float
    call_count: int
    cap_usd: float


def read_state(date_stamp: str | None = None) -> BudgetState:
    p = _budget_path(date_stamp)
    if not p.exists():
        return BudgetState(
            date_stamp=date_stamp or _utc_date_stamp(),
            spent_usd=0.0,
            call_count=0,
            cap_usd=_resolve_cap_usd(None),
        )
    raw = json.loads(p.read_text())
    return BudgetState(
        date_stamp=raw["date_stamp"],
        spent_usd=float(raw.get("spent_usd", 0.0)),
        call_count=int(raw.get("call_count", 0)),
        cap_usd=float(raw.get("cap_usd", _resolve_cap_usd(None))),
    )


def write_state(state: BudgetState) -> None:
    p = _budget_path(state.date_stamp)
    p.write_text(
        json.dumps(
            {
                "date_stamp": state.date_stamp,
                "spent_usd": state.spent_usd,
                "call_count": state.call_count,
                "cap_usd": state.cap_usd,
            },
            indent=2,
        )
    )


def check_and_reserve(
    cost_estimate_usd: float,
    *,
    cap_override: float | None = None,
    skip_combined_cap: bool = False,
) -> BudgetState:
    """Pre-call check. Raises `DiscoveryBudgetExceeded` (defined in
    `adapter.py`) if the cap would be exceeded by this call's
    estimated cost. Otherwise records the reservation and returns
    the post-state.

    Per spec §13.2 the **combined** acquisition cap is consulted
    BEFORE the per-provider Exa cap. This catches the
    Exa-spend-fine-but-combined-with-Browserbase-over case the
    per-provider cap can't see. Pass ``skip_combined_cap=True``
    only from test paths that have already monkeypatched the
    total-cap behavior.

    Idempotency note: the reservation is "optimistic" — if the
    actual cost diverges, the caller can `record_actual(...)` to
    correct. Today the Exa per-call cost is deterministic enough
    that the optimistic reservation matches actual within ±5%.
    """
    # Local import to avoid a circular module dependency.
    from .adapter import DiscoveryBudgetExceeded  # noqa: PLC0415

    if not skip_combined_cap:
        # Combined acquisition cap consulted first; raises
        # DailyAcquisitionBudgetExceeded (which is a separate
        # exception type so the caller can distinguish per-provider
        # vs combined exhaustion).
        from acquisition.search import assert_total_budget_ok  # noqa: PLC0415
        assert_total_budget_ok(cost_estimate_usd)

    cap_usd = _resolve_cap_usd(cap_override)
    state = read_state()
    state.cap_usd = cap_usd
    next_spent = state.spent_usd + cost_estimate_usd
    if next_spent > cap_usd:
        raise DiscoveryBudgetExceeded(
            f"Exa daily budget exceeded: would spend ${next_spent:.4f} "
            f"on top of ${state.spent_usd:.4f} (cap=${cap_usd:.2f}). "
            "Wait until UTC midnight or raise EXA_DAILY_BUDGET_USD."
        )
    state.spent_usd = next_spent
    state.call_count += 1
    write_state(state)
    return state


def record_actual(diff_usd: float) -> BudgetState:
    """Adjust today's spend by `diff_usd` (signed). Use after a call
    completes and the actual cost is known to refine the optimistic
    reservation."""
    state = read_state()
    state.spent_usd = max(0.0, state.spent_usd + diff_usd)
    write_state(state)
    return state
