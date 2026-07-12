"""Midnight Oil run receipt — the honest delivery surface (ask #13).

The operator's vision (ask #13): *"...autonomous research sub-agent swarm mode
called 'midnight oil' where users can engage in a deep research without needing
to be in the workstation; all they need to do is set a time of work and goals (and
the system provides the user a recommended price ceiling to approve) then the
agent goes off to execute that task."* The spine is complete: the operator
approves a ceiling (#1849), the planner schedules phases (#1854), each phase clears
the execution gate (#1842), and the ledger tracks actuals (#1841). But an UNATTENDED
run has a trust problem the attended paths do not: **the operator was not watching.**
When they return, the system owes them an honest accounting — did the swarm honor
the ceiling? what did it produce? where did it stop, and why? THIS module is that
accounting: the pure receipt that turns a plan + per-phase actuals into a single
honest delivery record.

**Why pure + import-free of the siblings.** The planner (#1854), gate (#1842), and
ledger (#1841) ship in separate off-main PRs. Hard-importing them would stack PRs
and break independent bar-cleanliness on a frozen main. Instead the receipt takes
the plan envelope + per-phase actual outcomes as injectable inputs (compatible
shapes); the execution layer that has all modules on hand assembles them. The
receipt owns the ONE thing no other module does: the **reconciliation** — actual
spend vs approved ceiling, planned vs executed phases, and the honest verdict on
whether the swarm stayed within the operator's trust bounds.

**The load-bearing invariants (each is a test):**

1. **The budget verdict is computed, never asserted.** ``within_budget`` is True
   iff ``actual_total_usd <= approved_ceiling_usd`` AND both are known. An unknown
   actual (provider didn't report cost) or an unknown ceiling → ``within_budget =
   None`` (never fabricated True — "we can't prove it stayed within" is not "it
   stayed within"). An over-budget run → ``within_budget = False`` (honest breach).
   This is the keystone: the operator approved a CEILING; the receipt must prove
   fidelity to it, never paper over a breach.
2. **An overage is surfaced explicitly, never hidden.** When ``actual > ceiling``,
   ``overage_usd`` is the real positive difference and ``within_budget = False``.
   A receipt that swallowed an overage would destroy the operator's trust in the
   unattended mode's whole premise.
3. **Stopped-at is the truth, never a summary.** The swarm may stop early for
   three honest reasons: the gate denied a phase (budget headroom exhausted), a
   phase raised a provider error, or the operator's time budget ran out. The
   receipt names the stopping phase + reason verbatim; it never claims "completed"
   when a phase was skipped. ``completion`` is one of ``completed`` (all planned
   phases ran) / ``stopped_early`` / ``unknown`` (cannot tell — e.g. the caller
   handed fewer actuals than planned with no stop reason).
4. **Planned-vs-executed is an exact count.** ``planned_phase_count`` and
   ``executed_phase_count`` partition reality; the difference is ``skipped_count``.
   A receipt never inflates executed to match planned.
5. **Every phase actual is auditable.** Each ``PhaseActual`` carries its ordinal,
   the gate's verdict (authorized/denied), the runner's outcome (ran/errored), the
   provider-reported cost (None if unreported), and any finding produced. The
   operator can drill into any phase, not trust a top-line number.
6. **Findings are carried verbatim, not summarized.** The swarm's produced
   artifacts (insights, questions, synthesis) are listed per-phase and in aggregate
   by reference id — the receipt never paraphrases a finding (that would be a
   fabrication risk). A finding count of 0 is shown honestly, not padded.
7. **Deterministic + pure.** Same (plan, actuals) → byte-identical receipt
   (content-addressed ``receipt_id``). No I/O, no clock, no dispatch. ``run_label``
   is caller-resolved.

**Composition (the MO trust loop):**

    operator approves ceiling (#1849) + planner schedules (#1854)
        ↓ swarm runs unattended, per-phase gate (#1842) + ledger (#1841)
    execution layer collects: plan envelope + [PhaseActual, ...]
        ↓
    build_run_receipt(...) → RunReceipt (THIS MODULE)
        ↓ operator returns
    honest accounting: within budget? produced what? stopped where?

The receipt is the contract between "the swarm ran while I was away" and "I can
trust what it did."
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


class RunReceiptError(ValueError):
    """A receipt input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ApprovedEnvelope:
    """What the operator approved for this run (the trust bounds).

    ``approved_ceiling_usd`` is the price ceiling from #1849 the operator OK'd.
    ``None`` means no ceiling was recorded — the receipt then cannot assert
    within_budget (unknown). ``planned_phase_count`` comes from #1854's plan.
    """

    approved_ceiling_usd: float | None
    planned_phase_count: int
    planned_duration_minutes: int
    goals: tuple[str, ...]


@dataclass(frozen=True)
class PhaseActual:
    """One phase's actual outcome after the swarm attempted it.

    ``gate_authorized`` is the gate's (#1842) verdict on this phase. ``ran`` is
    whether the runner actually executed (a denied phase has ran=False).
    ``actual_cost_usd`` is the provider-reported spend (None if unreported — the
    receipt never invents 0). ``finding_refs`` are opaque ids the execution layer
    resolves to real artifacts; the receipt carries them verbatim.
    """

    ordinal: int
    goal_index: int
    gate_authorized: bool
    ran: bool
    errored: bool
    actual_cost_usd: float | None
    finding_refs: tuple[str, ...] = ()
    stop_reason: str = ""  # "" = no stop here; set on the phase where the swarm halted


@dataclass(frozen=True)
class RunReceipt:
    """The honest delivery record for one unattended MO run."""

    receipt_id: str  # content-addressed over (envelope, actuals)
    run_label: str  # caller-resolved human label (e.g. "Midnight Oil 2026-W29 #3")
    envelope: ApprovedEnvelope
    phase_actuals: tuple[PhaseActual, ...]
    executed_phase_count: int
    skipped_phase_count: int
    actual_total_usd: float | None  # None if any phase cost unreported
    within_budget: bool | None  # None when actual or ceiling unknown
    overage_usd: float | None  # positive when over; None when within or unknown
    completion: str  # completed / stopped_early / unknown
    stopped_at_ordinal: int | None  # the phase where the swarm halted (None if completed)
    stopped_reason: str
    total_finding_refs: tuple[str, ...]
    honesty_notes: tuple[str, ...] = field(default_factory=tuple)


def _actual_total(actuals: tuple[PhaseActual, ...]) -> float | None:
    """Sum reported costs. None if ANY ran-phase cost is unreported (honest)."""
    total = 0.0
    for actual in actuals:
        if actual.ran:
            if actual.actual_cost_usd is None:
                return None
            total += actual.actual_cost_usd
    return total


def _stopped_at(actuals: tuple[PhaseActual, ...]) -> tuple[int | None, str]:
    """Find the phase where the swarm halted, and its reason.

    A stop is the LAST phase whose ``stop_reason`` is non-empty. Returns
    (ordinal, reason). If no phase carries a stop_reason AND all planned phases
    ran, the run completed (None, ""). If fewer actuals than planned and no
    explicit stop, it's "unknown" — the receipt refuses to guess.
    """
    for actual in reversed(actuals):
        if actual.stop_reason.strip():
            return actual.ordinal, actual.stop_reason.strip()
    return None, ""


def _receipt_id(envelope: ApprovedEnvelope, actuals: tuple[PhaseActual, ...]) -> str:
    payload = json.dumps(
        {
            "ceiling": envelope.approved_ceiling_usd,
            "planned_phases": envelope.planned_phase_count,
            "planned_minutes": envelope.planned_duration_minutes,
            "goals": list(envelope.goals),
            "actuals": [
                {
                    "ord": a.ordinal,
                    "g": a.goal_index,
                    "auth": a.gate_authorized,
                    "ran": a.ran,
                    "err": a.errored,
                    "cost": a.actual_cost_usd,
                    "refs": list(a.finding_refs),
                    "stop": a.stop_reason,
                }
                for a in actuals
            ],
        },
        sort_keys=True,
    )
    return "mo-receipt-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_run_receipt(
    *,
    run_label: str,
    envelope: ApprovedEnvelope,
    phase_actuals: list[PhaseActual],
) -> RunReceipt:
    """Assemble the honest delivery receipt for one unattended MO run.

    Pure: no I/O, no clock, no dispatch. Reconciles actuals against the approved
    envelope. The caller (execution layer) supplies the plan envelope + the
    collected per-phase outcomes; this module computes the verdict.
    """
    if not run_label.strip():
        raise RunReceiptError("run_label must be non-empty")
    if envelope.planned_phase_count < 1:
        raise RunReceiptError("planned_phase_count must be >= 1")
    if not envelope.goals:
        raise RunReceiptError("envelope.goals must be non-empty")

    actuals = tuple(phase_actuals)
    # ordinals must be unique and in order
    seen_ordinals: set[int] = set()
    for actual in actuals:
        if actual.ordinal in seen_ordinals:
            raise RunReceiptError(f"duplicate phase ordinal {actual.ordinal}")
        seen_ordinals.add(actual.ordinal)
    ordinals = [a.ordinal for a in actuals]
    if ordinals != sorted(ordinals):
        raise RunReceiptError("phase ordinals must be in ascending order")

    executed = sum(1 for a in actuals if a.ran)
    skipped = envelope.planned_phase_count - len(actuals)
    if skipped < 0:
        raise RunReceiptError(
            f"more actuals ({len(actuals)}) than planned ({envelope.planned_phase_count})"
        )

    actual_total = _actual_total(actuals)
    ceiling = envelope.approved_ceiling_usd

    notes: list[str] = []

    # Budget verdict — computed, never asserted (invariant #1).
    if actual_total is None or ceiling is None:
        within_budget: bool | None = None
        overage: float | None = None
        if actual_total is None:
            notes.append("actual spend unknown — at least one phase cost unreported")
        if ceiling is None:
            notes.append("no approved ceiling recorded — cannot assert within-budget")
    elif actual_total > ceiling:
        within_budget = False
        overage = actual_total - ceiling
        notes.append(f"OVER BUDGET by ${overage:.4f} (ceiling ${ceiling:.4f})")
    else:
        within_budget = True
        overage = None

    # Completion — the truth, never a summary (invariant #3).
    stopped_ordinal, stopped_reason = _stopped_at(actuals)
    if stopped_ordinal is not None:
        completion = "stopped_early"
    elif len(actuals) < envelope.planned_phase_count:
        # fewer actuals than planned, no explicit stop reason -> unknown
        completion = "unknown"
        notes.append(
            f"only {len(actuals)} of {envelope.planned_phase_count} phases reported, "
            "with no stop reason — completion unknown"
        )
    else:
        completion = "completed"

    # A denied or errored phase without an explicit stop_reason is surfaced honestly.
    for actual in actuals:
        if (not actual.gate_authorized or actual.errored) and not actual.stop_reason.strip():
            if actual.errored:
                notes.append(
                    f"phase {actual.ordinal} errored without a recorded stop reason"
                )
            elif not actual.gate_authorized:
                notes.append(
                    f"phase {actual.ordinal} was denied by the gate (budget headroom exhausted)"
                )

    total_finding_refs: tuple[str, ...] = ()
    for actual in actuals:
        total_finding_refs = total_finding_refs + actual.finding_refs

    return RunReceipt(
        receipt_id=_receipt_id(envelope, actuals),
        run_label=run_label,
        envelope=envelope,
        phase_actuals=actuals,
        executed_phase_count=executed,
        skipped_phase_count=skipped,
        actual_total_usd=actual_total,
        within_budget=within_budget,
        overage_usd=overage,
        completion=completion,
        stopped_at_ordinal=stopped_ordinal,
        stopped_reason=stopped_reason,
        total_finding_refs=total_finding_refs,
        honesty_notes=tuple(notes),
    )


__all__ = [
    "RunReceiptError",
    "ApprovedEnvelope",
    "PhaseActual",
    "RunReceipt",
    "build_run_receipt",
]
