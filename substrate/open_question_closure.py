r"""Open-question closure — is the research converging, or question-farming?

Operator vision (ask #1): *"I want to live in my research workstation ... and I
want the workstation to record the valuable data, insights, and questions
recursively that informs all prompts."* The recursive note-taker generates open
questions as its engine — each is a seed for a deeper chase. But recursion only
DELIVERS value when questions CLOSE: an open question that never resolves is an
infinite loop, not progress. ``open_question_closure`` measures the artifact's
AGGREGATE convergence — across ALL its open questions (escalated or not, planned
or spontaneous), what fraction resolved vs remain open? The headline "is this
research converging on answers or farming open questions forever?" signal.

**Genuinely distinct (different object + scope):**

* ``plan_resolution`` (#1937): were the PLAN's sub-questions resolved? (the
  approved cascade plan — PLAN scope, resolved via ``resolved_by`` graph edges)
* ``recursion_closure`` (#1961): did the escalated questions' child chases come
  back with findings? (ESCALATED-ONLY scope — reserved child investigations)
* ``escalation_linkage`` (#1941): did escalated questions get a chase scheduled?
  (STRUCTURAL — was a reservation made at all)
* ``research_yield`` (#1944): the insight/question COUNT balance (delivery vs
  recursion shape — a RATIO of counts, not resolution)
* THIS (``open_question_closure``): the artifact's AGGREGATE resolution rate
  across ALL its open questions (ALL scope — the headline convergence signal)

``plan_resolution`` and ``recursion_closure`` are scoped (plan / escalated); this
is the WHOLE-ARTIFACT convergence. ``research_yield`` counts insights-vs-questions
but never asks whether the questions CLOSED (a delivery-heavy artifact with 0
resolved questions is still question-farming — the questions just never got
answered). A research artifact converging on answers has a rising closure rate;
one stuck in a loop has a flat/low one. That signal is this axis.

**The measurement (hard to vary):**

Given the artifact's open questions, each tagged with a resolved state:

* ``resolved_count`` = questions with ``resolved == True``
* ``open_count`` = questions with ``resolved == False`` (still unanswered)
* ``total_questions = resolved_count + open_count``
* ``closure_rate = resolved_count / total_questions`` in ``[0, 1]`` (1.0 = every
  question closed; 0.0 = none did)

**Verdict:**

* ``unknown`` — ``total_questions == 0`` (no open questions recorded — defer; an
  artifact with no questions to resolve cannot be assessed for convergence; never
  fabricated as "fully closed")
* ``converging`` — ``closure_rate >= converged_threshold`` (default ``0.60`` —
  most questions resolved; the research is closing its loops; boundary inclusive)
* ``stalled`` — ``closure_rate <= stalled_threshold`` (default ``0.20`` — few or
  no questions resolved; the research is farming questions, not closing them;
  boundary inclusive)
* ``partial`` — between the thresholds (some resolution — mid-convergence)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict when there are no questions — an artifact
  with zero open questions is not "fully closed" (defer; it may simply have
  produced no questions, which is a different signal carried by ``research_yield``).
* ``closure_rate`` is ``None`` when ``total_questions == 0`` (defer, never ``0.0``
  — a zero-question artifact is NOT a 0%-resolved artifact).
* ``closure_rate == 0.0`` is a REAL ``stalled`` verdict: an artifact with open
  questions and zero resolutions is measured stalled, NOT ``unknown`` (the
  questions were recorded; they just never closed).
* a question must carry a non-empty ``question_id`` (the route layer maps it to
  the graph node); duplicates raise (ambiguous data).
* ``resolved`` is a caller-provided boolean (the route layer derives it from
  ``resolved_by`` graph edges — this axis stays pure: no DB, no graph read).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``OpenQuestion`` input
shape (the route layer adapts 1:1 from the artifact's ``ArtifactQuestion`` list +
the ``resolved_by`` edges read from the DB). Pure-Python: stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_CONVERGED_THRESHOLD: float = 0.60
_DEFAULT_STALLED_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class OpenQuestion:
    """One open question with its resolution state. Pure input.

    ``resolved`` is caller-derived (the route layer reads resolved_by graph edges
    from the DB); this axis stays pure and receives the boolean.
    """

    question_id: str
    resolved: bool


@dataclass(frozen=True)
class OpenQuestionClosureReport:
    """The open-question closure verdict. Advisory, pure."""

    total_questions: int
    resolved_count: int
    open_count: int
    closure_rate: float | None  # resolved/total; None when no questions
    converged_threshold: float
    stalled_threshold: float
    verdict: str  # unknown | converging | partial | stalled
    notes: tuple[str, ...]
    authority: str = "advisory"


class OpenQuestionClosureError(ValueError):
    """An open-question-closure input violates a load-bearing invariant."""


def measure_open_question_closure(
    questions: Sequence[OpenQuestion],
    *,
    converged_threshold: float = _DEFAULT_CONVERGED_THRESHOLD,
    stalled_threshold: float = _DEFAULT_STALLED_THRESHOLD,
) -> OpenQuestionClosureReport:
    """Measure the artifact's aggregate open-question closure rate.

    ``questions`` are the artifact's open questions with their resolved state.
    ``converged_threshold`` is the closure_rate at/above which the research is
    converging (default 0.60).
    ``stalled_threshold`` is the closure_rate at/below which it is stalled
    (default 0.20).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= converged_threshold <= 1.0:
        raise OpenQuestionClosureError(
            f"converged_threshold must be in [0,1], got {converged_threshold!r}"
        )
    if not 0.0 <= stalled_threshold <= 1.0:
        raise OpenQuestionClosureError(
            f"stalled_threshold must be in [0,1], got {stalled_threshold!r}"
        )
    if stalled_threshold > converged_threshold:
        raise OpenQuestionClosureError(
            f"stalled_threshold ({stalled_threshold}) cannot exceed "
            f"converged_threshold ({converged_threshold})"
        )

    # Validate question ids (non-empty; duplicates ambiguous).
    seen_ids: set[str] = set()
    for question in questions:
        if not question.question_id.strip():
            raise OpenQuestionClosureError(
                f"question_id must be non-empty, got {question.question_id!r}"
            )
        if question.question_id in seen_ids:
            raise OpenQuestionClosureError(
                f"duplicate question_id {question.question_id!r}"
            )
        seen_ids.add(question.question_id)

    total = len(questions)
    resolved_count = sum(1 for q in questions if q.resolved)
    open_count = total - resolved_count

    # No questions -> unknown (defer — an artifact with no questions is not
    # "fully closed"; closure_rate is None, never 0.0).
    if total == 0:
        return _report(
            0, 0, 0, None, converged_threshold, stalled_threshold, "unknown",
            [
                "open-question closure measures the artifact's AGGREGATE resolution "
                "rate across ALL its open questions (the convergence signal); "
                "distinct from plan_resolution #1937 (plan sub-questions), "
                "recursion_closure #1961 (escalated child chases), "
                "escalation_linkage #1941 (scheduling), research_yield #1944 "
                "(count balance — never asks if questions CLOSED)",
                "verdict unknown — zero open questions recorded (defer; an artifact "
                "with no questions is not 'fully closed' — closure_rate is None, "
                "never fabricated 0.0)",
            ],
        )

    closure_rate = resolved_count / total

    if closure_rate >= converged_threshold:
        verdict = "converging"
    elif closure_rate <= stalled_threshold:
        verdict = "stalled"
    else:
        verdict = "partial"

    notes: list[str] = [
        "open-question closure measures the artifact's AGGREGATE resolution rate "
        "across ALL its open questions (escalated or not, planned or spontaneous) "
        "— the headline convergence signal; distinct from plan_resolution #1937 "
        "(plan sub-questions) and recursion_closure #1961 (escalated child chases) "
        "which are scoped; THIS is whole-artifact",
        "closure_rate = resolved_count / total_questions in [0,1] (1.0 = every "
        "question closed, 0.0 = none did); resolved is caller-derived from "
        "resolved_by graph edges (this axis stays pure — no DB/graph read)",
        "verdict: converging (closure_rate >= converged_threshold, boundary "
        "inclusive — research closing its loops), stalled (<= stalled_threshold — "
        "question-farming, not closing), partial (mid-convergence)",
        "unknown when total_questions == 0 (defer — not 'fully closed'; an artifact "
        "with no questions cannot be assessed for convergence); closure_rate 0.0 is "
        "a REAL stalled verdict (questions recorded but none resolved), NOT unknown",
    ]
    notes.append(
        f"verdict {verdict}: {resolved_count} resolved, {open_count} open of "
        f"{total} total, closure_rate {closure_rate:.0%}; converged_threshold "
        f"{converged_threshold:.0%}, stalled_threshold {stalled_threshold:.0%}"
    )

    return _report(
        total, resolved_count, open_count, closure_rate,
        converged_threshold, stalled_threshold, verdict, notes,
    )


def _report(
    total: int,
    resolved_count: int,
    open_count: int,
    closure_rate: float | None,
    converged_threshold: float,
    stalled_threshold: float,
    verdict: str,
    notes: list[str],
) -> OpenQuestionClosureReport:
    return OpenQuestionClosureReport(
        total_questions=total,
        resolved_count=resolved_count,
        open_count=open_count,
        closure_rate=closure_rate,
        converged_threshold=converged_threshold,
        stalled_threshold=stalled_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
