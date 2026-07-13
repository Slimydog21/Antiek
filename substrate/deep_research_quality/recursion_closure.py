"""Recursion closure — did the reserved child resolve the parent question?

Operator vision (ask #1): *"send subagents to chase questions as I interrogate,
assess, and wrestle with the information ... and record the valuable data,
insights, and questions recursively that informs all prompts."* The recursion is
the heart of the workstation: an open question is escalated, a child investigation
is reserved to chase it, the child runs and returns findings. But NOTHING measures
whether that chase actually CLOSED — did the child's findings address the parent
question? An escalated question whose reserved child comes back empty or off-topic
is a FAILED recursion: wasted budget, an open loop masquerading as progress. The
operator, wrestling with the information, needs to see which chases paid off and
which are still open.

No current axis measures this. ``escalation_linkage`` (#1941) measures whether an
escalated question got a RESERVATION (did the chase get scheduled?) — it stops one
step short: it never checks whether the reserved child DELIVERED.
``resolution_candidates`` (#1946) DISCOVERS insight→question lexical candidates
across ARBITRARY prior artifacts (many-to-many discovery) — it does not verify the
SPECIFIC child reserved via ``reserved_child_investigation_id``.
``trajectory`` (#1952) measures tree TOPOLOGY (depth, breadth, structural
resolution rate) — not content closure. THIS is the missing check: for each
escalated question with a reserved child, does the child's insights lexically cover
the parent question's distinctive terms?

**The measurement (hard to vary).** For each open question on the parent artifact:

* Skip if not escalated (not a recursion candidate — excluded, never fabricated).
* Skip if escalated but has no ``reserved_child_investigation_id`` (that's the
  #1941 leak — an escalated question with no chase reserved; reported separately).
* If it has a reservation, look up the child in the supplied ``children`` map
  (``reserved_child_investigation_id -> ResearchArtifactBody``):
  - Child NOT in map → ``orphaned`` (reservation made but child not found / not
    completed — an open loop; the operator sees the dangling reservation).
  - Child in map but has zero insights → ``empty_child`` (the chase ran but
    returned nothing — a failed recursion).
  - Child in map with insights: compute ``closure_ratio = |question_terms ∩
    child_insight_terms| / |question_terms|`` (the fraction of the question's
    distinctive vocabulary covered by ANY of the child's insights — recall over
    the child's combined finding text).
    - ``>= closure_threshold`` (default 0.50) → ``resolved`` (the chase
      addressed the question — closure achieved).
    - below → ``unresolved`` (child exists and has findings, but they don't
      cover the question — a misdirected chase).

The module reports:

* ``resolved_count`` / ``unresolved_count`` / ``orphaned_count`` /
  ``empty_child_count`` (the closure verdicts).
* ``closure_rate = resolved / (resolved + unresolved + empty_child)`` — the
  fraction of ACTUALLY-RUN chases that closed (``None`` when none ran). Orphaned
  reservations are excluded from the denominator (they never ran — including them
  would conflate "didn't run" with "ran but failed").
* ``unescalated_count`` / ``unreserved_count`` (the excluded subsets, carried
  through for honesty).
* per-question ``QuestionClosure`` (``node_id``, ``reserved_child_id``,
  ``closure_ratio``, ``verdict``, ``uncovered_terms`` — auditable).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content words
(glue + interrogatives stripped), NO stemming, NO synonymy. A child that
paraphrases the answer (same meaning, different words) may score low — that is the
precision/recall tradeoff, the SAME conservative direction as twin_fidelity (#1954)
and twin_question_support (#1959): this detector prefers flagging a paraphrase
(false positive) over certifying a closed loop that isn't (false negative — that
would hide a genuinely-open question behind a phony closure). The operator confirms
downstream.

**Honesty rules (load-bearing):**

* ``closure_rate`` is ``None`` when zero chases ran (no resolved + unresolved +
  empty_child — defer — never ``0.0`` or ``1.0``).
* Unescalated and unreserved questions are EXCLUDED from the rate (carried as
  counts; they are not recursion outcomes — fabricating a verdict on them would
  conflate "didn't chase" with "chased and failed").
* Orphaned reservations are excluded from the ``closure_rate`` denominator (a
  reservation that never produced a child investigation did not "run"; counting it
  as a failed closure would punish scheduling rather than delivery — that's #1941's
  lane, not this axis's).
* ``closure_ratio`` is in ``[0.0, 1.0]``; ``uncovered_terms`` is the set
  difference (auditable — exactly which question terms the child's findings lack).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock,
  no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
``children`` map is a plain ``dict[str, ResearchArtifactBody]`` input (the route
layer reads the child investigations by following ``reserved_child_investigation_id``
from the graph DB).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_CLOSURE_THRESHOLD: float = 0.50

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "why", "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "other", "such", "own", "same", "too", "do", "does", "did",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + interrogatives stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


class RecursionClosureError(ValueError):
    """A recursion-closure input violates a load-bearing invariant."""


@dataclass(frozen=True)
class QuestionClosure:
    """One escalated question's recursion-closure verdict."""

    node_id: str
    reserved_child_id: str | None
    closure_ratio: float | None  # None if orphaned/empty_child (not content-measurable)
    verdict: str  # resolved | unresolved | orphaned | empty_child | unmeasurable | unreserved | unescalated
    uncovered_terms: tuple[str, ...]  # question terms absent from child findings


@dataclass(frozen=True)
class RecursionClosureReport:
    """The parent's recursion-closure profile. Advisory, pure."""

    artifact_id: str
    resolved_count: int
    unresolved_count: int
    orphaned_count: int
    empty_child_count: int
    unmeasurable_count: int  # child ran but question all-glue (lexically unmeasurable)
    unreserved_count: int  # escalated but no reservation (the #1941 leak)
    unescalated_count: int  # not escalated (excluded from recursion)
    closure_rate: float | None  # resolved / ran; None when zero ran
    question_closures: tuple[QuestionClosure, ...]
    closure_threshold: float
    verdict: str  # closed | partial | open | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_recursion_closure(
    parent: ResearchArtifactBody,
    children: dict[str, ResearchArtifactBody],
    *,
    closure_threshold: float = _DEFAULT_CLOSURE_THRESHOLD,
) -> RecursionClosureReport:
    """Measure whether the parent's escalated questions were resolved by their children.

    ``parent`` is the artifact whose recursion is being measured. ``children`` maps
    each ``reserved_child_investigation_id`` to the child ``ResearchArtifactBody``
    that was run to chase it (the route layer supplies this by following the
    reservation ids from the graph DB). Returns a
    :class:`RecursionClosureReport` with per-question closure + the overall rate.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= closure_threshold <= 1.0:
        raise RecursionClosureError(
            f"closure_threshold must be in [0,1], got {closure_threshold!r}"
        )

    per_question: list[QuestionClosure] = []
    resolved = 0
    unresolved = 0
    orphaned = 0
    empty_child = 0
    unreserved = 0
    unescalated = 0
    unmeasurable = 0

    for q in parent.open_questions:
        if not q.escalated:
            per_question.append(
                QuestionClosure(
                    node_id=q.node_id,
                    reserved_child_id=q.reserved_child_investigation_id,
                    closure_ratio=None,
                    verdict="unescalated",
                    uncovered_terms=(),
                )
            )
            unescalated += 1
            continue

        child_id = q.reserved_child_investigation_id
        if not child_id:
            per_question.append(
                QuestionClosure(
                    node_id=q.node_id,
                    reserved_child_id=None,
                    closure_ratio=None,
                    verdict="unreserved",
                    uncovered_terms=(),
                )
            )
            unreserved += 1
            continue

        child = children.get(child_id)
        if child is None:
            per_question.append(
                QuestionClosure(
                    node_id=q.node_id,
                    reserved_child_id=child_id,
                    closure_ratio=None,
                    verdict="orphaned",
                    uncovered_terms=(),
                )
            )
            orphaned += 1
            continue

        q_terms = _distinctive_terms(q.text)
        child_terms = frozenset[str]().union(
            *(_distinctive_terms(ins.text) for ins in child.insights)
        ) if child.insights else frozenset()

        if not child.insights:
            per_question.append(
                QuestionClosure(
                    node_id=q.node_id,
                    reserved_child_id=child_id,
                    closure_ratio=None,
                    verdict="empty_child",
                    uncovered_terms=tuple(sorted(q_terms)),
                )
            )
            empty_child += 1
            continue

        if not q_terms:
            # Question has no distinctive terms (all-glue) — can't measure lexical
            # closure. Distinct from unresolved (a content failure): this question is
            # lexically unmeasurable, so it is excluded from the rate denominator
            # (never fabricated as a failed closure).
            per_question.append(
                QuestionClosure(
                    node_id=q.node_id,
                    reserved_child_id=child_id,
                    closure_ratio=None,
                    verdict="unmeasurable",
                    uncovered_terms=(),
                )
            )
            unmeasurable += 1
            continue

        overlap = q_terms & child_terms
        ratio = len(overlap) / len(q_terms)
        uncovered = tuple(sorted(q_terms - child_terms))

        if ratio >= closure_threshold:
            verdict = "resolved"
            resolved += 1
        else:
            verdict = "unresolved"
            unresolved += 1

        per_question.append(
            QuestionClosure(
                node_id=q.node_id,
                reserved_child_id=child_id,
                closure_ratio=ratio,
                verdict=verdict,
                uncovered_terms=uncovered,
            )
        )

    ran = resolved + unresolved + empty_child
    closure_rate = resolved / ran if ran else None

    if closure_rate is None:
        artifact_verdict = "unknown"
    elif closure_rate >= 0.70:
        artifact_verdict = "closed"
    elif closure_rate >= 0.40:
        artifact_verdict = "partial"
    else:
        artifact_verdict = "open"

    notes: list[str] = [
        "recursion closure measures whether an escalated question's RESERVED CHILD "
        "investigation came back with findings that address the question — the recursion's "
        "success metric; escalation_linkage #1941 checks scheduling (did the chase get a "
        "reservation?), THIS checks delivery (did the reserved child resolve the question?)",
        "closure_ratio = overlap(question_terms, any child insight terms) / "
        "len(question_terms); >= threshold resolved, below unresolved, child-missing = "
        "orphaned (open loop), child-empty = empty_child (failed recursion); uncovered_terms "
        "is the auditable evidence",
        "closure_rate excludes orphaned reservations (a reservation that never ran is a "
        "scheduling leak = #1941's lane, not a failed closure) and unescalated/unreserved "
        "questions (not recursion outcomes — fabricating a verdict on them would conflate "
        "'didn't chase' with 'chased and failed')",
        "lexical floor (no stemming/synonymy): a child that paraphrases the answer may score "
        "low — prefers flagging a paraphrase (false positive) over certifying a phony closure "
        "that hides an open question (false negative); a semantic check confirms downstream",
    ]
    if ran == 0:
        notes.append(
            f"no chases ran (resolved+unresolved+empty_child=0); {orphaned} orphaned, "
            f"{unreserved} unreserved, {unescalated} unescalated of "
            f"{len(parent.open_questions)} question(s) — closure is not measurable "
            "(defer — never fabricated)"
        )
    else:
        notes.append(
            f"closure rate {closure_rate:.0%}: {resolved} resolved, {unresolved} "
            f"unresolved, {empty_child} empty-child, {unmeasurable} unmeasurable, "
            f"{orphaned} orphaned of "
            f"{len(parent.open_questions)} question(s) -> verdict {artifact_verdict}"
        )

    return RecursionClosureReport(
        artifact_id=parent.investigation_id,
        resolved_count=resolved,
        unresolved_count=unresolved,
        orphaned_count=orphaned,
        empty_child_count=empty_child,
        unmeasurable_count=unmeasurable,
        unreserved_count=unreserved,
        unescalated_count=unescalated,
        closure_rate=closure_rate,
        question_closures=tuple(per_question),
        closure_threshold=closure_threshold,
        verdict=artifact_verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "QuestionClosure",
    "RecursionClosureError",
    "RecursionClosureReport",
    "measure_recursion_closure",
]
