"""Problem-question coverage — does the output answer the question it was asked?

Operator vision: *"the highest quality deep research product in the world"* + the
research-workstation ask (*"I want to live in my research workstation ... wrestle
with the information in front of me"*). A deep-research artifact that is beautifully
cited, well-synthesized, and broadly sourced can still **drift** — it answers a
related-but-wrong question, leaving the stated problem question partially
unaddressed. None of the other quality axes catch this: ``citation_density`` asks
"grounded?", ``grounding_completeness`` asks "synthesis present?",
``source_diversity`` asks "broad evidence?" — none ask "did you answer the question
you were asked?" This module is that axis.

**The score (hard to vary).** Coverage is the fraction of the problem question's
DISTINCTIVE terms that appear in the artifact's output (insight texts + synthesis).
A term is distinctive once stop-words are stripped and case/whitespace normalized,
so "what is the impact of scaling laws on reasoning" contributes
``{scaling, laws, reasoning}`` (``impact`` is a stop-word here). The score is the
literal ratio ``matched_distinctive_terms / total_distinctive_terms`` in ``[0, 1]``
-- nothing approximated, nothing invented. It is a coverage floor, not a relevance
judgment: a term can appear lexically without the output truly engaging it, so a
high score is necessary but not sufficient for "answered the question."

**Unmatched terms are the signal.** The report lists exactly WHICH distinctive
question-terms the output never mentions -- the operator sees the drift
concretely ("you asked about reasoning, but the output never says reasoning") and
can decide whether to re-run, refine the prompt, or accept the gap. This is the
"understand what worked and what didn't" the operator named.

**Honest scope.** This is a LEXICAL check -- it cannot judge semantic relevance
(an output can discuss "reasoning" using the synonym "inference" and score as a
miss). Semantic relevance is an LLM-judge concern, honestly out of scope for a pure
function; the ``notes`` say so explicitly. Pretending to verify relevance
lexically would be the opposite of quality.

**Honesty rules (load-bearing):**
* ``measured=False`` when the problem question has no distinctive terms (empty,
  or stop-words only) -- coverage of nothing is unknown, never fabricated. The
  report defers rather than invent a score.
* ``measured=False`` when the output has no text to search (no insights and no
  synthesis) -- there is nothing to cover the question with.
* Deterministic and pure: same artifact in -> same report out. No LLM, no
  network, no clock, no mutation. ``authority`` is always ``"advisory"``.
* ``matched_terms`` and ``unmatched_terms`` are exposed verbatim (auditable), and
  the score is the exact ratio of the two set sizes -- no black-box relevance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stop-words stripped so the question's function words do not dilute the score.
# Kept short and intentional: these are the high-frequency English function words
# that carry no research signal. Domain terms ("impact", "effect") are excluded
# from stop-words on purpose -- a question explicitly asking about "impact" or
# "effect" should be checked for those words.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "to", "in", "on", "for", "with", "and", "or", "but", "not",
        "this", "that", "these", "those", "it", "its", "as", "at", "by",
        "from", "into", "than", "then", "so", "such", "do", "does", "did",
        "will", "would", "can", "could", "should", "may", "might", "must",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "about", "between", "through", "during", "above", "below", "over",
        "under", "again", "further", "there", "here", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "no", "nor", "only",
        "own", "same", "very", "just", "if", "because", "while", "until",
    }
)


class ProblemQuestionCoverageError(ValueError):
    """A coverage input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ProblemQuestionCoverageReport:
    """The problem-question coverage verdict for one artifact. Advisory, pure."""

    investigation_id: str
    score: float  # matched/total distinctive terms in [0, 1]; 0.0 when not measurable
    measured: bool  # False when the question has no distinctive terms OR output is empty
    total_distinctive_terms: int  # distinctive terms extracted from the problem question
    matched_terms: tuple[str, ...]  # distinctive terms found in the output (sorted)
    unmatched_terms: tuple[str, ...]  # distinctive terms NOT found in the output (sorted)
    notes: tuple[str, ...]
    authority: str = "advisory"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _distinctive_terms(text: str) -> list[str]:
    """Lowercased non-stop-word tokens, de-duplicated, order-preserving.

    Distinctive terms are what make a question *research-y*: stripping stop-words
    means the score measures coverage of the question's signal words, not its
    grammar. Order-preserving dedup keeps the question's own term order for the
    matched/unmatched lists (auditable), while set semantics drive the score.
    """
    seen: set[str] = set()
    terms: list[str] = []
    for tok in _tokenize(text):
        if tok in _STOP_WORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
    return terms


def _output_terms(body: ResearchArtifactBody) -> set[str]:
    """The set of all tokens in the artifact's insight texts + synthesis."""
    pieces: list[str] = [insight.text for insight in body.insights]
    if body.synthesis_excerpt is not None:
        pieces.append(body.synthesis_excerpt)
    text = " ".join(pieces)
    return set(_tokenize(text))


def score_problem_question_coverage(
    body: ResearchArtifactBody,
) -> ProblemQuestionCoverageReport:
    """Score how much of the problem question the artifact's output covers. Pure.

    Returns a :class:`ProblemQuestionCoverageReport`. ``measured=False`` when the
    problem question has no distinctive terms (empty / stop-words only) OR the
    output has no searchable text. The ``score`` is the fraction of the question's
    distinctive terms that appear in the output; ``unmatched_terms`` lists the drift.
    """
    if not body.problem_question.strip():
        raise ProblemQuestionCoverageError(
            "problem_question must be non-empty; cannot measure coverage of nothing"
        )

    question_terms = _distinctive_terms(body.problem_question)
    output_vocab = _output_terms(body)

    notes: list[str] = [
        "score is lexical coverage: the fraction of the problem question's "
        "distinctive (non-stop-word) terms present in the output; a coverage "
        "floor, not semantic relevance",
        "semantic relevance (synonyms, paraphrase) is an LLM-judge concern, "
        "out of scope for this pure function",
    ]

    if not question_terms:
        return ProblemQuestionCoverageReport(
            investigation_id=body.investigation_id,
            score=0.0,
            measured=False,
            total_distinctive_terms=0,
            matched_terms=(),
            unmatched_terms=(),
            notes=tuple(
                notes
                + [
                    "problem question has no distinctive terms (empty after "
                    "stop-word removal); coverage is unmeasurable"
                ]
            ),
        )

    if not output_vocab:
        return ProblemQuestionCoverageReport(
            investigation_id=body.investigation_id,
            score=0.0,
            measured=False,
            total_distinctive_terms=len(question_terms),
            matched_terms=(),
            unmatched_terms=tuple(sorted(question_terms)),
            notes=tuple(
                notes
                + [
                    "output has no searchable text (no insights, no synthesis); "
                    "nothing to cover the question with"
                ]
            ),
        )

    matched = [t for t in question_terms if t in output_vocab]
    unmatched = [t for t in question_terms if t not in output_vocab]
    score = len(matched) / len(question_terms)

    if unmatched:
        notes.append(
            f"DRIFT: {len(unmatched)} of {len(question_terms)} distinctive "
            f"question term(s) absent from the output — "
            + ", ".join(sorted(unmatched))
        )
    else:
        notes.append(
            f"all {len(question_terms)} distinctive question term(s) present in "
            "the output (lexical floor; semantic relevance not verified)"
        )

    return ProblemQuestionCoverageReport(
        investigation_id=body.investigation_id,
        score=score,
        measured=True,
        total_distinctive_terms=len(question_terms),
        matched_terms=tuple(sorted(matched)),
        unmatched_terms=tuple(sorted(unmatched)),
        notes=tuple(notes),
    )


__all__ = [
    "ProblemQuestionCoverageError",
    "ProblemQuestionCoverageReport",
    "score_problem_question_coverage",
]
