"""Discovery layer — sits upstream of the URL adapter.

Per `docs/integration_exa_browserbase.md` §3, the discovery layer
proposes URLs but does NOT write to the substrate graph. Promotion
to the graph (via `acquisition/urls/adapter.ingest_url`) is operator-
mediated and emitted as `DiscoverySelectedPayload`.

Module layout (Wedge 1 ships Exa only; future siblings extend here):

    acquisition/search/
        __init__.py                — this module + combined budget cap
        exa/
            client.py              — typed Exa HTTP client (httpx)
            adapter.py             — discover() + promote_discovery()
            budget.py              — Exa daily budget sidecar

Public surface re-exports the operator-facing names from the Exa
adapter for ergonomic import (`from acquisition.search import discover`).

This module also owns the **combined acquisition-layer budget cap**
per spec §13.2: total spend across Exa + Browserbase + future
providers is bounded at ``substrate.constants.TOTAL_ACQUISITION_BUDGET_USD``
(default $10/day). Each provider's sidecar is summed before any
per-provider cap is consulted; the combined cap fires
``DailyAcquisitionBudgetExceeded`` with no silent fallback.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Optional

from .exa.adapter import (
    DiscoveryBudgetExceeded,
    DiscoveryPromotionResult,
    DiscoveryProposed,
    discover,
    promote_discovery,
)


class DailyAcquisitionBudgetExceeded(RuntimeError):
    """Raised when the combined acquisition-layer spend across all
    providers (Exa + Browserbase + future) would exceed
    `TOTAL_ACQUISITION_BUDGET_USD` for the current UTC day.

    Per spec §13.2: there is NO silent throttle, no silent provider
    swap. The operator either waits for UTC midnight or raises the
    cap by setting `ANTIEK_TOTAL_ACQUISITION_BUDGET_USD` in the env.
    """


def _resolve_total_cap_usd(cap_override: float | None) -> float:
    if cap_override is not None:
        return float(cap_override)
    v = os.environ.get("ANTIEK_TOTAL_ACQUISITION_BUDGET_USD")
    if v:
        try:
            parsed = float(v)
            if parsed < 0:
                raise ValueError("negative")
            return parsed
        except ValueError:
            pass
    from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD
    return float(TOTAL_ACQUISITION_BUDGET_USD)


def _budget_dir() -> Path:
    base = os.environ.get("ANTIEK_HOME")
    if base:
        return Path(base) / "budgets"
    return Path.home() / ".antiek" / "budgets"


def _utc_date_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def current_total_spend_usd(date_stamp: str | None = None) -> float:
    """Sum spend across every provider sidecar for the current UTC
    day. Format-driven: any file matching
    ``<provider>_<date>.json`` with a numeric ``spent_usd`` field
    counts. New providers extend by writing to the same sidecar
    convention — no code change here required.
    """
    stamp = date_stamp or _utc_date_stamp()
    bdir = _budget_dir()
    if not bdir.exists():
        return 0.0
    total = 0.0
    for f in bdir.glob(f"*_{stamp}.json"):
        try:
            data = json.loads(f.read_text())
            total += float(data.get("spent_usd", 0.0))
        except (ValueError, OSError):
            continue
    return total


def assert_total_budget_ok(
    next_call_cost_usd: float,
    *,
    cap_override: float | None = None,
) -> float:
    """Pre-call check enforced at the package level. Sums today's
    spend across all provider sidecars; if the next call would push
    the total past the combined cap, raises
    `DailyAcquisitionBudgetExceeded`. Returns the post-call total
    (informational; the per-provider sidecar still records the
    actual reservation).

    Callers should consult this BEFORE their per-provider
    ``check_and_reserve`` — fail fast on the combined cap when the
    sum-of-providers would be exceeded, even if no single provider's
    cap is exceeded yet.
    """
    cap = _resolve_total_cap_usd(cap_override)
    current = current_total_spend_usd()
    projected = current + next_call_cost_usd
    if projected > cap:
        raise DailyAcquisitionBudgetExceeded(
            f"Combined acquisition daily budget would be exceeded: "
            f"current=${current:.4f}, next=${next_call_cost_usd:.4f}, "
            f"cap=${cap:.2f}. Wait until UTC midnight or raise "
            "ANTIEK_TOTAL_ACQUISITION_BUDGET_USD."
        )
    return projected


def default_discovery_events_dir() -> str:
    """Resolve the discovery-events sidecar directory.

    Per spec §14.1: discovery events live in a separate JSONL file
    from substrate events so the proposal-trail audit doesn't drown
    out substrate events. The directory is:

      - ``$ANTIEK_DISCOVERY_EVENTS_DIR`` if set
      - else ``$ANTIEK_HOME/discovery_events`` if ANTIEK_HOME is set
      - else ``~/.antiek/discovery_events``

    Creating the directory on first use is the caller's responsibility
    (matches the `default_events_dir` convention in the event log).
    """
    explicit = os.environ.get("ANTIEK_DISCOVERY_EVENTS_DIR")
    if explicit:
        p = Path(os.path.expanduser(explicit))
    elif os.environ.get("ANTIEK_HOME"):
        p = Path(os.environ["ANTIEK_HOME"]) / "discovery_events"
    else:
        p = Path.home() / ".antiek" / "discovery_events"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


__all__ = [
    "DailyAcquisitionBudgetExceeded",
    "DiscoveryBudgetExceeded",
    "DiscoveryPromotionResult",
    "DiscoveryProposed",
    "assert_total_budget_ok",
    "current_total_spend_usd",
    "default_discovery_events_dir",
    "discover",
    "promote_discovery",
]
