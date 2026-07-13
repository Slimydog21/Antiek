r"""Question specificity — is the research question well-posed enough to answer?

Operator vision (ask #1): *"...I want to live in my research workstation and send
subagents to chase questions as I Interrogate, assess, and wrestle with the
information infront of me..."* The recursive-chase loop is findings→questions→chase.
But the loop's INPUT quality is never measured: is the QUESTION itself well-posed? A
research question that is too VAGUE (few distinctive terms — "tell me about AI")
spawns an unfocused chase that returns a sprawling, unanswerable result. A question
that is too NARROW (over-stuffed with terms — a keyword soup) is brittle, locking the
chase into one exact phrasing and missing the related context that would answer it.
A SPECIFIC question (a focused band of distinctive terms — enough to bound the
search, not so many it becomes a lookup) is what a thought partner should help the
operator write. Measuring question specificity BEFORE the chase runs is the input-
quality gate the workstation needs to be a genuine thought partner.

**Genuinely distinct from the question/insight surface:**

* ``problem_question_coverage`` (#1929): does the OUTPUT answer the stated question
  (drift detection — coverage of question terms in the output). Measures the ANSWER.
* ``insight_question_derivation`` (#1989): do the open questions arise from the
  artifact's insights (internal derivation link). Measures QUESTION-INSIGHT linkage.
* ``question_redundancy`` (#1980): does the artifact ask the same question twice
  (intra-question duplication). Measures question-question repetition.
* ``twin_question_support`` (#1959): are the twin's questions grounded in the source.

NONE measures the QUESTION'S OWN specificity — is it well-posed? This is logically
PRIOR to all of them: #1929 asks "did you answer it?" (requires a well-posed
question to be meaningful); THIS asks "was the question answerable in the first
place?" A vague question can score perfect coverage (#1929 high — the output
mentions all the few vague terms) yet be unanswerable (THIS vague). A specific
question can score low coverage (#1929 low — the output drifted) yet be well-posed
(THIS specific). Answering and being-answerable are different; both matter.

**The measurement (hard to vary).** Tokenize the question to distinctive terms
(stop-word-stripped, NO stemming/synonymy — the lexical floor pinned across all text
axes). The distinctive-term count is the question's "bandwidth":

* ``distinctive_term_count`` — the number of unique non-stop-word tokens. This is the
  core signal: how much lexical subject matter the question carries.
* ``total_token_count`` — raw token count (for context; a question with 50 tokens and
  3 distinctive terms is stop-word-heavy/gluey).
* ``distinctive_ratio`` — distinctive_term_count / total_token_count (information
  density — a high ratio means every word carries subject; a low ratio means gluey
  padding).
* ``distinctive_terms`` — the actual terms (auditable — the operator sees what
  subject the question bounds).
* ``has_interrogative`` — does the question contain an interrogative anchor (what /
  how / why / when / which / whether / who / can / does / is)? A research question
  without an interrogative is a topic, not a question — surfaced (not a verdict
  driver, but a structural signal).

**Verdict (distinct honest states, never collapsed):**

* zero distinctive terms (empty / all stop-words / only punctuation) -> ``unmeasurable``
  (the question carries no lexical subject — defer, never fabricated ``specific``).
* ``distinctive_term_count < min_terms`` (default 3) -> ``vague`` (too few terms to
  bound a chase — "tell me about AI" with one term spawns an unfocused sprawl).
* ``distinctive_term_count > max_terms`` (default 12) -> ``over_narrow`` (a keyword
  soup — locks the chase into one exact phrasing, brittle to paraphrase).
* otherwise (min_terms <= count <= max_terms) -> ``specific`` (a focused band — enough
  to bound the search, not so many it becomes a lookup). A REAL measured verdict, NOT
  the default.

**Honesty rules (load-bearing):**

* ``unmeasurable`` never fabricates ``specific`` when there are no distinctive terms
  (a question with no lexical subject is not "specific" — it is nothing).
* ``specific`` is a REAL measured verdict (the term count fell in the focused band),
  NOT the default — ``unmeasurable`` means nothing-to-measure; ``specific`` means
  measured-and-focused. Never collapsed.
* ``distinctive_ratio`` is ``None`` when ``unmeasurable`` (defer — never ``0.0``).
* LEXICAL FLOOR: NO stemming (scale != scales), NO synonymy (impact != affect), stop-
  words stripped so grammatical glue does not inflate the term count. Interrogatives
  are treated as stop-words for the distinctive count (a question's "what" is
  structural glue, not subject) but their PRESENCE is captured separately as
  ``has_interrogative``.
* ``distinctive_terms`` carried verbatim (auditable — the operator sees the exact
  subject band).
* thresholds must be positive integers with ``min_terms <= max_terms`` (raises).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted terms, reproducible output).
* import-free of off-main siblings (own plain-string input; route layer adapts 1:1
  from the artifact's problem_question field).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "QuestionSpecificityReport",
    "measure_question_specificity",
]

_DEFAULT_MIN_TERMS = 3
_DEFAULT_MAX_TERMS = 12

# Stop-words: grammatical glue that does not carry subject. Interrogatives are
# included here (a question's "what" is structural, not subject) but their presence
# is tracked separately via _INTERROGATIVES for has_interrogative.
_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "in",
        "on", "at", "by", "for", "with", "about", "to", "from", "as", "is",
        "are", "was", "were", "be", "been", "being", "do", "does", "did",
        "have", "has", "had", "will", "would", "could", "should", "may", "might",
        "can", "shall", "must", "this", "that", "these", "those", "it", "its",
        "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
        "my", "your", "his", "our", "their", "what", "which", "who", "whom",
        "whose", "when", "where", "why", "how", "whether", "there", "here",
        "than", "so", "such", "not", "no", "nor", "too", "very", "into", "over",
        "under", "again", "more", "most", "some", "any", "all", "both", "each",
        "few", "other", "own", "same", "s", "t", "just", "out", "up", "down",
        "off", "because", "while", "during", "before", "after", "above", "below",
    }
)

_INTERROGATIVES = frozenset(
    {"what", "which", "who", "whom", "whose", "when", "where", "why", "how",
     "whether", "can", "does", "is", "are", "will", "could", "should"}
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class QuestionSpecificityReport:
    """The question-specificity (input-quality) verdict. Advisory, pure.

    Attributes:
        distinctive_term_count: unique non-stop-word tokens.
        total_token_count: raw token count (context for density).
        distinctive_ratio: distinctive/total; ``None`` when ``unmeasurable``.
        distinctive_terms: the actual terms, sorted (auditable).
        has_interrogative: does the question carry an interrogative anchor?
        min_terms: focused-band lower bound.
        max_terms: focused-band upper bound.
        verdict: ``specific`` / ``vague`` / ``over_narrow`` / ``unmeasurable``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    distinctive_term_count: int
    total_token_count: int
    distinctive_ratio: float | None
    distinctive_terms: tuple[str, ...]
    has_interrogative: bool
    min_terms: int
    max_terms: int
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_question_specificity(
    question: str,
    *,
    min_terms: int = _DEFAULT_MIN_TERMS,
    max_terms: int = _DEFAULT_MAX_TERMS,
) -> QuestionSpecificityReport:
    r"""Measure whether a research question is specific enough to be answerable.

    ``question`` is the research question text. Returns a
    :class:`QuestionSpecificityReport` classifying it as vague / specific /
    over_narrow / unmeasurable.

    Raises:
        ValueError: if ``min_terms`` or ``max_terms`` are not positive integers,
            or ``min_terms > max_terms``.
    """
    if not isinstance(min_terms, int) or min_terms < 1:
        raise ValueError(f"min_terms must be a positive int; got {min_terms}")
    if not isinstance(max_terms, int) or max_terms < 1:
        raise ValueError(f"max_terms must be a positive int; got {max_terms}")
    if min_terms > max_terms:
        raise ValueError(
            f"min_terms ({min_terms}) must be <= max_terms ({max_terms})"
        )

    if question is None:
        question = ""

    tokens = _TOKEN_RE.findall(question.lower())
    total_token_count = len(tokens)

    # Distinctive terms = tokens that are not stop-words (interrogatives included
    # as stop-words for the subject count).
    distinctive = frozenset(t for t in tokens if t not in _STOP_WORDS)
    distinctive_terms = tuple(sorted(distinctive))
    distinctive_term_count = len(distinctive)

    # Interrogative presence (structural signal, separate from subject count).
    has_interrogative = any(t in _INTERROGATIVES for t in tokens)

    if distinctive_term_count == 0:
        return QuestionSpecificityReport(
            distinctive_term_count=0,
            total_token_count=total_token_count,
            distinctive_ratio=None,
            distinctive_terms=(),
            has_interrogative=has_interrogative,
            min_terms=min_terms,
            max_terms=max_terms,
            verdict="unmeasurable",
            notes=("question carries no distinctive subject terms",),
        )

    distinctive_ratio = distinctive_term_count / total_token_count

    if distinctive_term_count < min_terms:
        verdict = "vague"
    elif distinctive_term_count > max_terms:
        verdict = "over_narrow"
    else:
        verdict = "specific"

    note_parts = [
        f"{distinctive_term_count} distinctive term(s); ratio {distinctive_ratio:.2f}",
    ]
    if not has_interrogative:
        note_parts.append("no interrogative anchor — a topic, not a question")

    return QuestionSpecificityReport(
        distinctive_term_count=distinctive_term_count,
        total_token_count=total_token_count,
        distinctive_ratio=distinctive_ratio,
        distinctive_terms=distinctive_terms,
        has_interrogative=has_interrogative,
        min_terms=min_terms,
        max_terms=max_terms,
        verdict=verdict,
        notes=tuple(note_parts),
    )
