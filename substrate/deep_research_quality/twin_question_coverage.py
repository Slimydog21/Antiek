"""Twin question coverage — did the twin surface the source's questions?

Operator vision (ask #4): *"every information asset ... has a twin document with
all the insights and questions proposed by that information document written by an
LLM."* The twin is the RECURSIVE NOTE-TAKER: it should lift every QUESTION the
source raises into its own ``open_questions``, because each one is a candidate
sub-investigation that sends a subagent chasing an answer. A question the source
raised that the twin DROPPED is invisible to the recursive engine — it never
becomes a child branch, and the knowledge graph silently loses a direction of
inquiry that the author thought worth asking. Coverage is the fuel-discovery
check: does the twin's note-taking RECALL the source's questions?

No current axis measures this. ``twin_question_support`` (#1959) measures question
PRECISION — does each twin open question have source support (or is it a phantom
the source never raised)? It does NOT measure question RECALL — did the twin
surface the questions the source actually asked? The two failure modes are
opposite: #1959 catches the twin INVENTING a question (a phantom chase); THIS
module catches the twin DROPPING a question (a lost branch). ``twin_coverage``
(#1964) measures insight RECALL (did the twin capture the source's insights) —
not question recall. THIS is the missing fourth cell of the twin quality matrix:
insight-precision (#1954), insight-recall (#1964), question-precision (#1959),
question-recall (this). Same content type (questions) as #1959, opposite
direction (recall vs precision) — an accepted distinctness criterion.

**The measurement (hard to vary).**

* Extract the source's explicit questions: ``?``-terminated segments of the source
  text (``re.split`` on ``?``, pairing each segment with its terminator — a
  sentence that ends in ``?`` is a question; trailing non-question text is not).
* For each source question: extract its distinctive terms (content words, glue
  stripped — the shared lexical floor of all quality/cross-reference modules).
* Compute the maximum Jaccard overlap between the source question's terms and
  EACH twin open question's terms: ``|S ∩ T| / |S ∪ T|``.
* A source question whose best twin Jaccard is ``>= capture_threshold`` (default
  0.50) is ``captured`` (the twin surfaced a near-duplicate); below is ``missed``
  (the twin's note-taking dropped it — a lost-branch signal).
* Source questions with no distinctive terms are ``unmeasurable`` (excluded from
  the rate, never fabricated — e.g. "why?" alone is all-glue).

The module reports:

* ``source_question_count`` / ``captured_count`` / ``missed_count`` /
  ``unmeasurable_count`` / ``twin_question_count``.
* ``capture_rate = captured / measurable`` (``None`` when there are no source
  questions or zero measurable).
* ``missed_questions`` — the actionable subset: a ``MissedQuestion(text, terms)``
  per dropped question, carrying the source question's distinctive terms as the
  auditable evidence (the vocabulary the twin should have surfaced a question
  about but did not).
* ``capture_threshold`` and ``verdict`` (``no_source_questions`` |
  ``unmeasurable`` | ``complete_capture`` | ``partial_capture`` | ``no_capture``).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content
words (glue stripped), NO stemming, NO synonymy. A paraphrased twin question (same
meaning, different words) may score below threshold and register as a miss — that
is the precision/recall tradeoff, the SAME conservative direction as
twin_coverage (#1964): this detector prefers flagging a paraphrase (false
positive miss) over certifying a dropped question as captured (false negative).
A dropped question certified as "captured" starves the knowledge graph of a
branch; a paraphrase flagged as "missed" is a minor inconvenience the operator
confirms downstream. The conservative error is the safe one.

**Honesty rules (load-bearing):**

* A source with NO ``?``-terminated segments is ``no_source_questions`` —
  ``capture_rate`` is ``None`` (nothing to recall, never fabricated ``0.0``).
* A source question with NO distinctive terms (empty or all-glue) is
  ``unmeasurable`` — excluded from the rate, carried through as a count. When all
  source questions are unmeasurable, ``capture_rate`` is ``None`` and the verdict
  is ``unmeasurable``.
* A source question that IS measurable but matches no twin question is an honest
  ``missed`` — ``capture_rate`` reflects the real 0.0 contribution. ``None``
  (nothing to measure) never collapses into ``0.0`` (measured, found nothing);
  ``no_capture`` is reserved for the latter.
* ``capture_rate`` is in ``[0.0, 1.0]``; ``missed_questions.terms`` is the
  auditable set difference for each miss.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The source
text is a plain ``str`` input (the route layer reads it from the asset store).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_CAPTURE_THRESHOLD: float = 0.50

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
    """Lowercase content words (grammatical glue + interrogatives stripped)."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


def _extract_questions(source_text: str) -> list[str]:
    """Return the ``?``-terminated segments of ``source_text`` (question text).

    ``re.split`` on ``?`` with a capture group yields ``[segment, "?", ...]``;
    we pair each segment with its terminator and drop empty/trailing text that
    has no closing ``?`` (non-question prose). The returned text carries its
    trailing ``?`` so it reads as a question in a report.
    """
    parts = re.split(r"([?])", source_text)
    questions: list[str] = []
    for idx in range(0, len(parts) - 1, 2):
        segment = parts[idx].strip()
        if segment:
            questions.append(segment + "?")
    return questions


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Symmetric term overlap in ``[0.0, 1.0]``; 0.0 when either set is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class TwinQuestionCoverageError(ValueError):
    """A twin-question-coverage input violates a load-bearing invariant."""


@dataclass(frozen=True)
class MissedQuestion:
    """A source question the twin failed to surface (the recall gap).

    ``distinctive_terms`` is the auditable evidence: the content words the twin
    should have lifted into an open question but did not.
    """

    text: str
    distinctive_terms: tuple[str, ...]


@dataclass(frozen=True)
class TwinQuestionCoverageReport:
    """The twin's question-recall profile. Advisory, pure."""

    artifact_id: str
    source_question_count: int
    captured_count: int
    missed_count: int
    unmeasurable_count: int
    twin_question_count: int
    capture_rate: float | None  # captured/measurable; None if no questions or zero measurable
    missed_questions: tuple[MissedQuestion, ...]
    capture_threshold: float
    verdict: str  # no_source_questions | unmeasurable | complete_capture | partial_capture | no_capture
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_twin_question_coverage(
    twin: ResearchArtifactBody,
    source_text: str,
    *,
    capture_threshold: float = _DEFAULT_CAPTURE_THRESHOLD,
) -> TwinQuestionCoverageReport:
    """Measure whether the twin surfaced the source's questions.

    ``twin`` is the LLM-generated twin (a ``ResearchArtifactBody``).
    ``source_text`` is the content the twin was generated from. Returns a
    :class:`TwinQuestionCoverageReport` with the recall rate and the dropped
    questions.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= capture_threshold <= 1.0:
        raise TwinQuestionCoverageError(
            f"capture_threshold must be in [0,1], got {capture_threshold!r}"
        )

    twin_term_sets = [
        _distinctive_terms(q.text) for q in twin.open_questions
    ]

    source_questions = _extract_questions(source_text)

    captured = 0
    missed = 0
    unmeasurable = 0
    missed_questions: list[MissedQuestion] = []

    for raw_question in source_questions:
        q_terms = _distinctive_terms(raw_question)
        if not q_terms:
            unmeasurable += 1
            continue

        best_overlap = 0.0
        for twin_terms in twin_term_sets:
            overlap = _jaccard(q_terms, twin_terms)
            if overlap > best_overlap:
                best_overlap = overlap

        if best_overlap >= capture_threshold:
            captured += 1
        else:
            missed += 1
            missed_questions.append(
                MissedQuestion(
                    text=raw_question,
                    distinctive_terms=tuple(sorted(q_terms)),
                )
            )

    measurable = captured + missed
    if not source_questions:
        capture_rate = None
        verdict = "no_source_questions"
    elif measurable == 0:
        capture_rate = None
        verdict = "unmeasurable"
    else:
        capture_rate = captured / measurable
        if capture_rate == 1.0:
            verdict = "complete_capture"
        elif capture_rate == 0.0:
            verdict = "no_capture"
        else:
            verdict = "partial_capture"

    notes: list[str] = [
        "twin question coverage measures whether the twin surfaced the SOURCE's "
        "questions into its open_questions — a dropped question is invisible to the "
        "recursive engine and silently starves the knowledge graph of a branch; "
        "twin_question_support #1959 checks question PRECISION (phantoms), this is "
        "the opposite RECALL direction, completing the twin quality matrix's "
        "fourth cell (insight-precision #1954, insight-recall #1964, "
        "question-precision #1959, question-recall this)",
        "source questions are ?-terminated segments; for each, best Jaccard "
        "overlap(source_terms, twin_terms) over all twin open questions; >= threshold "
        "captured, below missed (lost-branch signal), no-distinctive-terms = "
        "unmeasurable (excluded from rate, never fabricated); missed_questions carries "
        "the dropped question's distinctive_terms as auditable evidence",
        "capture_rate = captured/measurable; no source questions -> no_source_questions "
        "(None), all unmeasurable -> unmeasurable (None), 1.0 -> complete_capture, 0.0 "
        "-> no_capture (the honest measured-zero, distinct from the deferred None)",
        "lexical floor (no stemming/synonymy): a paraphrased twin question may score "
        "below threshold and register as a miss — this detector prefers flagging a "
        "paraphrase (false positive miss) over certifying a dropped question as "
        "captured (false negative); a semantic check confirms downstream",
    ]
    if not source_questions:
        notes.append(
            "no ?-terminated source questions found; question recall is not "
            "measurable (defer — never fabricated)"
        )
    elif measurable == 0:
        notes.append(
            f"{unmeasurable} source question(s), all with no distinctive terms "
            "(empty or all-glue); question recall is not measurable "
            "(defer — never fabricated)"
        )
    else:
        notes.append(
            f"question capture rate {capture_rate:.0%}: {captured} captured, "
            f"{missed} missed, {unmeasurable} unmeasurable of "
            f"{len(source_questions)} source question(s) against "
            f"{len(twin.open_questions)} twin question(s) at threshold "
            f"{capture_threshold:.0%} -> verdict {verdict}"
        )

    return TwinQuestionCoverageReport(
        artifact_id=twin.investigation_id,
        source_question_count=len(source_questions),
        captured_count=captured,
        missed_count=missed,
        unmeasurable_count=unmeasurable,
        twin_question_count=len(twin.open_questions),
        capture_rate=capture_rate,
        missed_questions=tuple(missed_questions),
        capture_threshold=capture_threshold,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "MissedQuestion",
    "TwinQuestionCoverageError",
    "TwinQuestionCoverageReport",
    "measure_twin_question_coverage",
]
