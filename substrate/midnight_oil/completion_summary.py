"""Midnight-Oil completion summary — the autonomous-run accountability surface.

Operator vision (ask #13): *"midnight oil" where users engage in deep research
without needing to be in the workstation; all they need to do is set a time of
work and goals (and the system provides a recommended price ceiling to approve)
then the agent goes off to execute that task.*

The operator sets goals + ceiling + time, then WALKS AWAY. When they return, the
run is done. The question they face: **did it deliver?** An autonomous run that
the operator cannot assess is a black box — they cannot trust it, cannot improve
it, cannot decide whether to run it again. The completion summary is the surface
that makes the run ACCOUNTABLE: one report showing what was asked, what was spent,
what was delivered, and whether the goals were met — with honest defer where
measurement is not yet possible.

**The verdict (hard to vary).** Composed from the run's request envelope (goals,
ceiling, time box) and its results (goal delivery, spend, artifacts):

* ``delivered`` — all measurable goals met, spend within ceiling, within time box.
* ``partial`` — some goals met, or spend/duration within bounds but not all goals.
* ``goal_gap`` — ≥1 measurable goal UNMET (the accountability signal — the run did
  not deliver on what was asked).
* ``over_budget`` — spend exceeded the ceiling (a SPEND violation — the reserve-
  before-spend ledger #720 should prevent this; if it appears, something leaked).
* ``over_time`` — duration exceeded the time box.
* ``unknown`` — no measurable goals AND no spend data (nothing to assess).

**Verdict priority (load-bearing).** A spend violation (``over_budget``) takes
PRIORITY over goal delivery — a run that met its goals but overspent is flagged
``over_budget`` so the leak surfaces. Similarly ``over_time`` surfaces before
goal gaps. The priority is: ``unknown`` > ``over_budget`` > ``over_time`` >
``goal_gap`` > ``partial`` > ``delivered``. Violations never bury under success.

**Honesty rules (load-bearing):**
* Unmeasurable goals are EXCLUDED from the delivery ratio (never penalized to 0).
  ``delivery_ratio = met / (met + partial + unmet)`` — only MEASURABLE goals count.
  This mirrors goal_delivery #1938's discipline.
* ``unknown`` when there are zero measurable goals AND zero spend — the run cannot
  be assessed. Never fabricated as ``delivered``.
* ``budget_utilization`` is ``spend / ceiling`` in ``[0.0, ∞)``; ``None`` if
  ceiling is 0 or unknown. A utilization > 1.0 IS the over-budget signal.
* ``time_utilization`` is ``actual_minutes / requested_minutes`` in ``[0.0, ∞)``;
  ``None`` if requested is 0.
* Every metric carried through verbatim (auditable breakdown).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings (load-bearing).** The midnight_oil contracts
(``MidnightOilRequest``, ``budget_ledger``) are NOT on frozen main yet. This
module takes the run's request + results as a frozen :class:`MOCompletionInputs`
dataclass (compatible shapes). The route layer fills it from the MO run's actual
artifacts when the foundation merges. Mirrors the #1937 / #1949 compatible-shape
pattern.
"""

from __future__ import annotations

from dataclasses import dataclass


class CompletionSummaryError(ValueError):
    """A completion-summary input violates a load-bearing invariant."""


@dataclass(frozen=True)
class MOCompletionInputs:
    """The request envelope + results for one completed (or stopped) MO run.

    The route layer fills this from the MO run's request + goal-delivery results +
    budget ledger. Every field is a raw metric — no off-main imports.
    """

    run_id: str
    # Request envelope (what the operator asked for)
    goal_count: int  # total goals set
    requested_minutes: int  # the time box
    price_ceiling_usd: float  # the approved spend ceiling
    # Results (what happened)
    goals_met: int  # measurable goals fully addressed
    goals_partial: int  # measurable goals partially addressed
    goals_unmet: int  # measurable goals not addressed
    goals_unmeasurable: int  # goals that could not be assessed (excluded from ratio)
    actual_spend_usd: float  # what was actually spent
    actual_minutes: int  # how long it ran
    artifacts_produced: int  # ResearchArtifactBody outputs


@dataclass(frozen=True)
class CompletionSummary:
    """The accountability surface for one MO run. Advisory, pure."""

    run_id: str
    verdict: str  # delivered | partial | goal_gap | over_budget | over_time | unknown
    delivery_ratio: float | None  # met/(met+partial+unmet); None if no measurable goals
    budget_utilization: float | None  # spend/ceiling; None if ceiling unknown/0
    time_utilization: float | None  # actual/requested; None if requested 0
    measurable_goal_count: int  # met + partial + unmet
    notes: tuple[str, ...]
    authority: str = "advisory"


def build_completion_summary(inputs: MOCompletionInputs) -> CompletionSummary:
    """Compose the MO run's request + results into one accountability verdict.

    Pure: no DB, no LLM, no clock, no mutation. Verdict priority: unknown >
    over_budget > over_time > goal_gap > partial > delivered (violations never
    bury under success).
    """
    if inputs.goal_count < 0:
        raise CompletionSummaryError(
            f"goal_count must be >= 0, got {inputs.goal_count!r}"
        )
    if inputs.price_ceiling_usd < 0:
        raise CompletionSummaryError(
            f"price_ceiling_usd must be >= 0, got {inputs.price_ceiling_usd!r}"
        )
    if inputs.actual_spend_usd < 0:
        raise CompletionSummaryError(
            f"actual_spend_usd must be >= 0, got {inputs.actual_spend_usd!r}"
        )
    if inputs.actual_minutes < 0 or inputs.requested_minutes < 0:
        raise CompletionSummaryError("durations must be >= 0")
    for label, val in (
        ("goals_met", inputs.goals_met),
        ("goals_partial", inputs.goals_partial),
        ("goals_unmet", inputs.goals_unmet),
        ("goals_unmeasurable", inputs.goals_unmeasurable),
    ):
        if val < 0:
            raise CompletionSummaryError(f"{label} must be >= 0, got {val!r}")

    measurable = inputs.goals_met + inputs.goals_partial + inputs.goals_unmet
    delivery_ratio: float | None = (
        inputs.goals_met / measurable if measurable else None
    )
    budget_util: float | None = (
        inputs.actual_spend_usd / inputs.price_ceiling_usd
        if inputs.price_ceiling_usd > 0
        else None
    )
    time_util: float | None = (
        inputs.actual_minutes / inputs.requested_minutes
        if inputs.requested_minutes > 0
        else None
    )

    notes: list[str] = [
        "the completion verdict is DESCRIPTIVE accountability, not a quality "
        "judgment — 'delivered' means goals were addressed and bounds respected, "
        "not that the research was good (quality is measured by the deep_research_"
        "quality axes); the operator judges the value",
        "verdict priority is unknown > over_budget > over_time > goal_gap > "
        "partial > delivered — a spend/time violation or unmet goal never buries "
        "under success",
    ]

    if measurable == 0 and inputs.actual_spend_usd == 0:
        verdict = "unknown"
        notes.append(
            "no measurable goals and no spend recorded; the run cannot be assessed "
            "(defer — never fabricated as delivered)"
        )
    elif budget_util is not None and budget_util > 1.0:
        verdict = "over_budget"
        notes.append(
            f"spend ${inputs.actual_spend_usd:.2f} exceeded ceiling "
            f"${inputs.price_ceiling_usd:.2f} ({budget_util:.0%} utilization) — "
            f"a SPEND VIOLATION; the reserve-before-spend ledger should prevent "
            f"this; if it appears, something leaked"
        )
    elif time_util is not None and time_util > 1.0:
        verdict = "over_time"
        notes.append(
            f"duration {inputs.actual_minutes}min exceeded time box "
            f"{inputs.requested_minutes}min ({time_util:.0%} utilization) — "
            f"the run overran its approved window"
        )
    elif inputs.goals_unmet > 0:
        verdict = "goal_gap"
        notes.append(
            f"{inputs.goals_unmet} of {measurable} measurable goal(s) UNMET — "
            f"the run did not deliver on what was asked; "
            f"{inputs.goals_met} met, {inputs.goals_partial} partial, "
            f"{inputs.goals_unmeasurable} unmeasurable (excluded from the ratio)"
        )
    elif delivery_ratio is not None and delivery_ratio < 1.0:
        verdict = "partial"
        notes.append(
            f"delivery ratio {delivery_ratio:.0%}: {inputs.goals_met} met, "
            f"{inputs.goals_partial} partial of {measurable} measurable goal(s); "
            f"within budget ({budget_util:.0%}) and time ({time_util:.0%}) but "
            f"not all goals fully addressed"
        )
    else:
        verdict = "delivered"
        spend_desc = f"{budget_util:.0%} of ceiling" if budget_util is not None else "ceiling unknown"
        time_desc = f"{time_util:.0%} of box" if time_util is not None else "time box unknown"
        notes.append(
            f"all {measurable} measurable goal(s) met; spend "
            f"{spend_desc}; time {time_desc}; "
            f"{inputs.artifacts_produced} artifact(s) produced"
        )

    return CompletionSummary(
        run_id=inputs.run_id,
        verdict=verdict,
        delivery_ratio=delivery_ratio,
        budget_utilization=budget_util,
        time_utilization=time_util,
        measurable_goal_count=measurable,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "CompletionSummary",
    "CompletionSummaryError",
    "MOCompletionInputs",
    "build_completion_summary",
]
