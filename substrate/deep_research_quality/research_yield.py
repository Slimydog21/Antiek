"""Research yield — does the artifact deliver findings, or just raise questions?

Operator vision (ask #1): the workstation records *"valuable data, insights, and
questions recursively that informs all prompts."* Insights and open questions are
both first-class in the canonical ``ResearchArtifactBody`` — insights are the
DELIVERY (what the research found), open questions are the RECURSION (what to chase
next). They are complementary, not interchangeable. But an artifact that produces
many open questions and few insights has not delivered research — it has catalogued
uncertainty. A question-farm (20 open questions, 2 insights) is the shape of an
investigation that stalled before finding anything; the operator reading it sees a
list of unknowns, not knowledge.

THIS module measures the BALANCE — the research-yield axis.

**Distinct from ``plan_resolution`` (#1937).** That module takes a PLAN
(``PlanQuestion`` graph node ids) + a resolved-set and asks *"were the plan's
sub-questions answered?"* (CONTENT resolution against an external plan). This
module takes the artifact's OWN ``insights`` and ``open_questions`` and asks *"does
the artifact deliver proportionally more answers than gaps?"* (STRUCTURAL balance
within one artifact). Different input (no external plan), different failure mode
(low delivery vs unresolved plan).

**Distinct from ``escalation_linkage`` (#1941).** That checks whether ESCALATED
questions carry chase reservations (the recursion-scheduling accountability). This
checks the INSIGHT-TO-QUESTION RATIO (the delivery-vs-recursion balance). An
artifact can have perfect escalation linkage yet still be a question-farm if it
raised 20 questions (all properly escalated) and produced 2 insights.

**The score (hard to vary).** ``yield_ratio`` is ``insights / (insights + open_questions)``:
the share of the artifact's informational mass that is a delivered finding rather than
an open question. ``1.0`` = all insights (pure delivery, no recursion seeded); ``0.0``
= all open questions (pure recursion, nothing delivered). The healthy band is neither
extreme — research both delivers AND seeds the next chase — so the report surfaces the
raw ratio and a graduated verdict rather than a single "good/bad" threshold.

**Honest scope (load-bearing).** This is a STRUCTURAL count, not a quality judgment
on the insights' content. Two brilliant insights + two brilliant questions (ratio
0.5) and two trivial insights + two trivial questions (ratio 0.5) score the same
here — the QUALITY of each is measured by the other axes. This module measures the
BALANCE, deliberately leaving content-quality to the content axes. It does NOT
prescribe the "right" ratio — the verdict bands are descriptive (delivery-heavy /
balanced / recursion-heavy / unknown), not normative; the operator decides what
balance fits their investigation.

**Honesty rules (load-bearing):**
* An artifact with no insights AND no open questions has ``yield_ratio = None``
  (never fabricated 0) — the balance of nothing is unknown. This is the empty-
  artifact defer.
* ``yield_ratio`` is in ``[0.0, 1.0]`` whenever it is not ``None``.
* Escalated questions are counted as open questions (they ARE open questions that
  were flagged for a deeper chase — escalation is a scheduling flag, not a
  resolution). A question escalated but not answered is still an open question.
* The verdict is graduated and descriptive:
  - ``delivery_heavy`` — ratio ≥ ``delivery_threshold`` (default 0.75): the artifact
    delivers far more than it defers.
  - ``recursion_heavy`` — ratio < ``recursion_threshold`` (default 0.25): the
    artifact defers far more than it delivers (the question-farm shape).
  - ``balanced`` — between the two thresholds.
  - ``unknown`` — no informational mass (yield_ratio None).
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_DELIVERY_THRESHOLD: float = 0.75
_DEFAULT_RECURSION_THRESHOLD: float = 0.25


class ResearchYieldError(ValueError):
    """A research-yield input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ResearchYieldReport:
    """The artifact's delivery-vs-recursion balance surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    insight_count: int
    open_question_count: int
    informational_mass: int  # insights + open_questions
    yield_ratio: float | None  # insights/mass in [0,1]; None if mass == 0
    verdict: str  # "delivery_heavy" | "balanced" | "recursion_heavy" | "unknown"
    delivery_threshold: float
    recursion_threshold: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_research_yield(
    artifact: ResearchArtifactBody,
    *,
    delivery_threshold: float = _DEFAULT_DELIVERY_THRESHOLD,
    recursion_threshold: float = _DEFAULT_RECURSION_THRESHOLD,
) -> ResearchYieldReport:
    """Measure the artifact's insight-to-question balance (research yield).

    ``artifact`` is the canonical knowledge-asset body. Returns a
    :class:`ResearchYieldReport` with the yield ratio and a descriptive verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 < delivery_threshold <= 1.0:
        raise ResearchYieldError(
            f"delivery_threshold must be in (0.0, 1.0], got {delivery_threshold!r}"
        )
    if (
        not recursion_threshold
        or not 0.0 <= recursion_threshold < delivery_threshold
    ):
        raise ResearchYieldError(
            f"recursion_threshold must be in [0.0, delivery_threshold), got "
            f"{recursion_threshold!r} (delivery_threshold={delivery_threshold!r})"
        )

    insight_count = len(artifact.insights)
    question_count = len(artifact.open_questions)
    mass = insight_count + question_count
    ratio: float | None = (insight_count / mass) if mass else None

    if ratio is None:
        verdict = "unknown"
    elif ratio >= delivery_threshold:
        verdict = "delivery_heavy"
    elif ratio < recursion_threshold:
        verdict = "recursion_heavy"
    else:
        verdict = "balanced"

    notes: list[str] = [
        "research yield is a STRUCTURAL count (insight-to-question ratio), not a "
        "content-quality judgment — the quality of each insight/question is "
        "measured by the content axes; this measures the delivery-vs-recursion "
        "balance only",
        "escalated questions count as open questions (escalation is a scheduling "
        "flag, not a resolution — a question escalated but unanswered is still open)",
    ]
    if mass == 0:
        notes.append(
            "no insights and no open questions; the delivery-vs-recursion balance "
            "is not measurable (defer)"
        )
    else:
        notes.append(
            f"yield ratio {ratio:.0%}: {insight_count} insight(s), "
            f"{question_count} open question(s) of {mass} informational mass -> "
            f"{verdict}"
        )

    return ResearchYieldReport(
        artifact_id=artifact.investigation_id,
        insight_count=insight_count,
        open_question_count=question_count,
        informational_mass=mass,
        yield_ratio=ratio,
        verdict=verdict,
        delivery_threshold=delivery_threshold,
        recursion_threshold=recursion_threshold,
        notes=tuple(notes),
    )


__all__ = [
    "ResearchYieldError",
    "ResearchYieldReport",
    "measure_research_yield",
]
