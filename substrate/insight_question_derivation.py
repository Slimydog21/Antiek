r"""Insight→question derivation — do the open questions arise from the insights?

Operator vision (asks #1/#4): *"...send subagents to chase questions as I
Interrogate, assess, and wrestle with the information... record the valuable data,
insights, and questions recursively..."* and the recursive note-taker generates
open questions as its engine — each a seed for a deeper chase. The derivation link
is the note-taker's CORE LOOP: findings (insights) should MOTIVATE what to chase
next (questions). A question that arises from an insight is DERIVED — it pushes
the frontier forward from a known finding. A question that shares no subject with
ANY insight is FLOATING — it asks about something the research never even surfaced
as a finding, so it is not driving the frontier; it is an orphan tangent.

**Genuinely distinct (different link):**

* ``twin_question_support`` (#1959): are the questions grounded in the SOURCE
  document (external — do they trace to what was read?). EXTERNAL.
* ``question_redundancy`` (#1980): are two QUESTIONS near-duplicates of each other
  (internal question-to-question — the recursion pollutant).
* ``plan_resolution`` (#1937): were the PLAN's questions answered (external plan).
* ``escalation_linkage`` (#1941): were ESCALATED questions assigned a chase
  (structural scheduling).
* ``insight_redundancy`` (#1939): are two INSIGHTS near-duplicates (internal
  insight-to-insight).
* THIS (``insight_question_derivation``): do the QUESTIONS derive from the
  artifact's OWN INSIGHTS (internal insight-to-question — the derivation link).

They are independent. A question can be grounded in the source (#1959 high, it
traces to what was read) yet FLOATING relative to the insights (the source
mentioned it, but the research never surfaced a finding about it, so the question
is not driving the current investigation forward). Conversely a question can be
derived from an insight (THIS high) yet weakly grounded in the source (#1959 low
— the insight is a synthesis/inference, and the question follows from it). The
external grounding and the internal derivation are different links; both matter for
a healthy recursive note-taker. The derivation ratio tells the platform whether the
question layer is driven by the finding layer (a coherent investigation) or
disconnected from it (orphan tangents that waste chase budget).

**The measurement (hard to vary).** Given the artifact's insights and open
questions (each a short text): a question is DERIVED when it shares at least
``min_overlap`` distinctive terms (stop-word-stripped, NO stemming/synonymy — the
lexical floor pinned across all text axes) with at least ONE insight. A question
sharing no distinctive term with any insight is FLOATING.

* ``derived_question_count`` / ``floating_question_count`` — the split.
* ``derivation_ratio = derived / total`` — in ``[0, 1]`` (0 = every question is an
  orphan tangent; 1 = every question traces to at least one finding).
* ``floating_questions`` — the specific floating question ids (auditable, so the
  platform can flag them for review before scheduling chases).
* ``orphan_insight_count`` — insights that seed NO question (the reverse
  direction: a finding that generated no follow-up — potentially an unexplored
  thread, not necessarily a defect, but surfaced for review).

**Verdict (distinct honest states, never collapsed):**

* zero measurable questions OR zero measurable insights -> ``unknown`` (defer —
  derivation cannot be assessed without both sides; never fabricated).
* ``derivation_ratio == 1.0`` -> ``fully_derived`` (every question traces to at
  least one finding — the coherent-investigation signal; a REAL measured verdict).
* ``derivation_ratio == 0.0`` (and both sides measurable) -> ``floating`` (every
  question is an orphan tangent — the investigation's question layer is
  disconnected from its finding layer; a REAL measured verdict).
* otherwise -> ``partially_derived`` (some questions derive, some float — the
  common middle ground).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when either side is empty (no questions OR no
  insights — derivation needs both).
* ``floating`` never collapses with ``unknown``: no-questions = unknown; questions-
  present-but-none-derive = floating (a REAL measured verdict).
* ``derivation_ratio`` is carried even at ``0.0`` (every question floating — a real
  signal, not deferred).
* all-glue insights/questions (only stop-words) are EXCLUDED (carried as
  ``unmeasurable_insight_count`` / ``unmeasurable_question_count``) — they share no
  distinctive terms, so the derivation link is structurally unmeasurable for them;
  fabricating a link would be dishonest.
* Distinct from insight_redundancy #1939 and question_redundancy #1980 (those
  measure intra-layer duplication; THIS measures cross-layer derivation). A high
  derivation_ratio is NOT high redundancy — derivation needs a shared SUBJECT
  anchor, not full duplication.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``InsightText`` and
``QuestionText`` input shapes (the route layer adapts 1:1 from the artifact's
insight and question lists). Pure-Python: stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_MIN_OVERLAP: int = 1

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "is", "are", "was", "were", "be", "been", "being", "am",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "of", "as", "this",
        "that", "these", "those", "it", "its", "they", "them", "their", "we",
        "us", "our", "you", "your", "he", "she", "him", "her", "his", "hers",
        "i", "me", "my", "mine", "which", "who", "whom", "what", "where", "why",
        "how", "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "also", "there", "here", "now", "any", "because", "while",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


@dataclass(frozen=True)
class InsightText:
    """One insight's text. Pure input."""

    insight_id: str
    text: str | None


@dataclass(frozen=True)
class QuestionText:
    """One open question's text. Pure input."""

    question_id: str
    text: str | None


@dataclass(frozen=True)
class InsightQuestionDerivationReport:
    """The insight-to-question derivation verdict. Advisory, pure."""

    measurable_insight_count: int
    measurable_question_count: int
    unmeasurable_insight_count: int
    unmeasurable_question_count: int
    derived_question_count: int
    floating_question_count: int
    derivation_ratio: float | None  # derived/total; None when unknown
    floating_question_ids: tuple[str, ...]  # sorted ids of floating questions
    orphan_insight_count: int  # insights seeding no question
    min_overlap: int
    verdict: str  # fully_derived | partially_derived | floating | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _distinctive_terms(text: str | None) -> frozenset[str]:
    if text is None:
        return frozenset()
    tokens = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in tokens if t not in _STOP_WORDS)


def measure_insight_question_derivation(
    insights: Sequence[InsightText],
    questions: Sequence[QuestionText],
    *,
    min_overlap: int = _DEFAULT_MIN_OVERLAP,
) -> InsightQuestionDerivationReport:
    r"""Measure whether open questions derive from the artifact's insights.

    A question is DERIVED when it shares at least ``min_overlap`` distinctive
    terms with at least one insight; otherwise FLOATING. Returns an
    :class:`InsightQuestionDerivationReport`.

    Raises:
        ValueError: if ``min_overlap`` is not positive.
    """
    if min_overlap < 1:
        raise ValueError(f"min_overlap must be positive; got {min_overlap}")

    insight_terms: dict[str, frozenset[str]] = {}
    unmeasurable_insights = 0
    for ins in insights:
        terms = _distinctive_terms(ins.text)
        if terms:
            insight_terms[ins.insight_id] = terms
        else:
            unmeasurable_insights += 1

    question_terms: dict[str, frozenset[str]] = {}
    unmeasurable_questions = 0
    for q in questions:
        terms = _distinctive_terms(q.text)
        if terms:
            question_terms[q.question_id] = terms
        else:
            unmeasurable_questions += 1

    measurable_insights = len(insight_terms)
    measurable_questions = len(question_terms)

    if measurable_questions == 0 or measurable_insights == 0:
        return InsightQuestionDerivationReport(
            measurable_insight_count=measurable_insights,
            measurable_question_count=measurable_questions,
            unmeasurable_insight_count=unmeasurable_insights,
            unmeasurable_question_count=unmeasurable_questions,
            derived_question_count=0,
            floating_question_count=0,
            derivation_ratio=None,
            floating_question_ids=(),
            orphan_insight_count=0,
            min_overlap=min_overlap,
            verdict="unknown",
            notes=("need both measurable insights and questions",),
        )

    insight_term_union: dict[str, frozenset[str]] = insight_terms
    derived_count = 0
    floating_ids: list[str] = []
    seeding_insights: set[str] = set()

    for q_id, q_terms in question_terms.items():
        is_derived = False
        for ins_id, ins_terms in insight_term_union.items():
            if len(q_terms & ins_terms) >= min_overlap:
                is_derived = True
                seeding_insights.add(ins_id)
                break  # one matching insight suffices for derivation
        if is_derived:
            derived_count += 1
        else:
            floating_ids.append(q_id)

    floating_ids.sort()
    floating_count = len(floating_ids)
    derivation_ratio = derived_count / measurable_questions
    orphan_insight_count = measurable_insights - len(seeding_insights)

    if derivation_ratio == 1.0:
        verdict = "fully_derived"
    elif derivation_ratio == 0.0:
        verdict = "floating"
    else:
        verdict = "partially_derived"

    notes = (
        f"{derived_count} of {measurable_questions} question(s) derived; "
        f"{floating_count} floating; {orphan_insight_count} orphan insight(s)",
    )

    return InsightQuestionDerivationReport(
        measurable_insight_count=measurable_insights,
        measurable_question_count=measurable_questions,
        unmeasurable_insight_count=unmeasurable_insights,
        unmeasurable_question_count=unmeasurable_questions,
        derived_question_count=derived_count,
        floating_question_count=floating_count,
        derivation_ratio=derivation_ratio,
        floating_question_ids=tuple(floating_ids),
        orphan_insight_count=orphan_insight_count,
        min_overlap=min_overlap,
        verdict=verdict,
        notes=notes,
    )
