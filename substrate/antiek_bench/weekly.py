"""Weekly cadence orchestrator — closes the recursive benchmark loop.

The one place the bench's dual outputs are composed into a week's evidence. Takes
a set of already-scored :class:`RunResult` objects for one ISO week, records each
to the tamper-evident ledger, and produces:

- the week's **view records** (for ``present_weekly_bench`` → the Settings panel), and
- the week's **usage events** (for ``propose_next_week_weights`` → next week's weights).

This is the **recursive loop edge** the operator named: *run → record → learn
weights → re-write the benchmark*. Without this module the scored verdicts go to
the ledger but never close into a week's evidence that feeds the next cycle.

Pure by construction: it takes caller-supplied run results (the actual model
invocation is the caller's job, via :mod:`runner`). The weight-proposal step is
an injectable :class:`WeightProposer` protocol so the real consumer
(``propose_next_week_weights`` from #810) plugs in without coupling; a default
Laplace implementation is provided for standalone testing.

``week_id`` follows the ISO week convention (``YYYY-Www``, matching view.py's
``2026-W28``). Deterministic: the same set of run results for the same week
always produces the same evidence.

Authority: ``weekly.py`` never dispatches models and never mutates spend. The
``live_dispatch_authorized`` / ``charge_executed`` flags come from each
``RunResult`` and are surfaced (not overridden) — an honest week with any unpaid
dispatch is flagged, never hidden.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .recorder import (
    UsageEvent,
    ViewRecord,
    append_to_ledger,
    record_verdict,
    week_incomplete,
    week_usage_events,
    week_view_records,
)
from .runner import RunResult


def iso_week_id(d: date | None = None) -> str:
    """ISO week label ``YYYY-Www`` (e.g. ``2026-W28``), matching view.py."""
    d = d or datetime.now(UTC).date()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


class WeightProposer(Protocol):
    """The weight-proposal boundary (the real consumer is propose_next_week_weights).

    Implementations take this week's usage events + prior weights and return
    next week's weights (failure-driven, summing to exactly 1.0).
    """

    def propose(
        self,
        *,
        events: list[UsageEvent],
        prior_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        ...


def default_laplace_weights(
    *,
    events: list[UsageEvent],
    prior_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Failure-driven Laplace weight proposal (sums to exactly 1.0).

    Each task's weight ∝ (failures + 1) / (total + n_tasks). More failures →
    more bench attention next week (the recursive self-rewriting edge). Tasks
    with no measured events get a uniform floor so new families are explored.
    Only real-bool ``success`` counts (None/unknown is ignored, mirroring
    ``_as_bool_success``).
    """

    fails: dict[str, int] = {}
    measured: dict[str, int] = {}
    for ev in events:
        if ev.success is None:
            continue  # pending/unknown — don't count
        measured[ev.task] = measured.get(ev.task, 0) + 1
        if ev.success is False:
            fails[ev.task] = fails.get(ev.task, 0) + 1
    tasks = sorted(set(measured) | set(prior_weights or {}))
    if not tasks:
        return {}
    scores = {t: float(fails.get(t, 0) + 1) for t in tasks}
    total = sum(scores.values())
    if total <= 0:
        n = len(tasks)
        return {t: round(1.0 / n, 8) for t in tasks}
    raw = {t: s / total for t, s in scores.items()}
    # Largest-remainder so weights sum to exactly 1.0 (conservation).
    return _largest_remainder(raw)


def _largest_remainder(weights: dict[str, float]) -> dict[str, float]:
    """Round fractions to 8 decimals so they sum to exactly 1.0."""
    scaled = {t: round(w, 8) for t, w in weights.items()}
    drift = round(1.0 - sum(scaled.values()), 8)
    if abs(drift) < 1e-12 or not scaled:
        return scaled
    # Distribute the rounding drift to the largest-weight task.
    largest = max(scaled, key=lambda t: scaled[t])
    scaled[largest] = round(scaled[largest] + drift, 8)
    return scaled


class WeekEvidence(BaseModel):
    """One week's composed evidence: the dual outputs + loop-closing weights."""

    model_config = {"frozen": True}

    week_id: str
    view_records: list[ViewRecord] = Field(default_factory=list)
    usage_events: list[UsageEvent] = Field(default_factory=list)
    incomplete: bool = False
    n_records: int = 0
    any_unauthorized_dispatch: bool = False
    next_week_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> WeekEvidence:
        if self.next_week_weights:
            total = round(sum(self.next_week_weights.values()), 8)
            if abs(total - 1.0) > 1e-9:
                raise ValueError(f"next_week_weights must sum to 1.0, got {total}")
        return self


def close_week(
    *,
    run_results: list[RunResult],
    ledger_path: Path,
    prior_weights: dict[str, float] | None = None,
    weight_proposer: WeightProposer | None = None,
) -> WeekEvidence:
    """Record a week's run results to the ledger and produce composed evidence.

    Each ``RunResult`` is turned into a tamper-evident record and appended. The
    week's view records + usage events are read back from the verified ledger
    (proving the round-trip). Next-week weights are proposed via the injected
    ``weight_proposer`` (or the default Laplace implementation).
    """


    ledger = ledger_path
    for result in run_results:
        append_to_ledger(
            record_verdict(result.verdict, week_id=result.week_id),
            ledger_path=ledger,
        )
    week_ids = {r.week_id for r in run_results}
    week_id = sorted(week_ids)[0] if week_ids else iso_week_id()

    view_records = week_view_records(ledger, week_id=week_id)
    usage_events = week_usage_events(ledger, week_id=week_id)
    incomplete = week_incomplete(ledger, week_id=week_id)
    n_records = len(view_records)
    any_unauthorized = any(
        not r.live_dispatch_authorized for r in run_results
    ) and bool(run_results)

    proposer = weight_proposer or _LaplaceProposer()
    next_weights = proposer.propose(
        events=usage_events,
        prior_weights=prior_weights,
    )

    return WeekEvidence(
        week_id=week_id,
        view_records=view_records,
        usage_events=usage_events,
        incomplete=incomplete,
        n_records=n_records,
        any_unauthorized_dispatch=any_unauthorized,
        next_week_weights=next_weights,
    )


class _LaplaceProposer:
    """Adapter so default_laplace_weights satisfies the WeightProposer protocol."""

    def propose(
        self,
        *,
        events: list[UsageEvent],
        prior_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        return default_laplace_weights(events=events, prior_weights=prior_weights)
