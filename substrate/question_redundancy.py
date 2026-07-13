r"""Question-redundancy — does the artifact ask the same question twice?

Operator vision (asks #1/#3/#4): *"record the valuable data, insights, and
questions recursively"* and the recursive note-taker generates open questions as
its engine — each a seed for a deeper chase. When artifacts are MERGED
(collective synthesis, twin-substrate merge, Midnight-Oil run-findings
promotion), questions from different sources can ask the same thing in different
wording. ``question_redundancy`` detects these near-duplicate questions.

**Genuinely distinct (different object):**

* ``insight_redundancy`` (#1939): near-duplicate INSIGHTS (findings) — the same
  CLAIM restated. Pollutes the knowledge graph with redundant findings.
* THIS (``question_redundancy``): near-duplicate QUESTIONS (open questions) — the
  same UNKNOWN asked twice. Pollutes the RECURSION engine: two chases scheduled
  for one underlying question = wasted budget, and the recursion never converges
  on a question it keeps re-asking.

Insights are FINDINGS (what was learned); questions are UNKNOWNS (what to chase).
They are structurally different objects. A merged artifact can have zero insight
redundancy (every finding is distinct) yet high question redundancy (three
questions all asking *"what is the cost per token?"* in different wording) — the
opposite also holds. The two failure modes require separate detection.

Question redundancy also dilutes every question-counting measurement: a research
artifact that appears to have 20 open questions (high ``research_yield`` question
mass, low ``open_question_closure`` convergence) may actually have 8 unique
questions — the rest are paraphrases. This axis surfaces that, so the recursion
engine dedupes before scheduling chases.

**The measurement (hard to vary):**

For every pair of open questions: **Jaccard** over their **distinctive terms**
(stop-word + interrogative stripped, NO stemming/synonymy — pinned, the same
lexical floor as the other text axes) = ``|A ∩ B| / |A ∪ B|``. Pairs >=
``threshold`` (default ``0.70`` — strict, catching near-exact paraphrases) are
flagged as redundant.

* ``redundant_pairs`` = flagged question pairs (both ``node_id``s + similarity +
  sorted shared terms — auditable)
* ``implicated_question_ids`` = the set of questions in ANY flagged pair
* ``redundancy_ratio = |implicated| / |total_questions|`` in ``[0,1]`` (the share
  of the question set implicated in a near-dup pair)
* ``max_similarity`` = the strongest pairwise signal, carried **even when below
  threshold** (never withheld — the operator sees the highest overlap regardless)

**Verdict:**

* ``unknown`` — fewer than two measurable questions (defer — redundancy across
  one/zero questions is vacuous; never fabricated as non-redundant)
* ``redundant`` — at least one flagged pair (``len(redundant_pairs) >= 1``)
* ``distinct`` — zero flagged pairs AND ``max_similarity >= 0`` (questions were
  measured and none near-duplicated — a REAL measured verdict, distinct from
  ``unknown``)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when there are fewer than two measurable questions
  — a single question cannot be redundant with itself (defer).
* ``distinct`` is a REAL measured verdict, NOT the default: questions were
  measured and none near-duplicated. ``unknown`` means not-enough-to-measure;
  ``distinct`` means measured-and-clean. Never collapsed.
* ``max_similarity`` is carried even when ``0.0`` (all-glue questions share
  nothing — a real measured signal) and even when below threshold (the operator
  sees the highest overlap regardless of whether it crossed the flag line).
* all-glue questions (only stop-words/interrogatives) are excluded — they share
  no distinctive terms, so they cannot near-duplicate by this measure (carried as
  ``unmeasurable_count``).
* ``redundancy_ratio`` is ``None`` when ``unknown`` (defer, never ``0.0`` — a
  single question is not "0% redundant").
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``OpenQuestionText`` input
shape (the route layer adapts 1:1 from the artifact's ``ArtifactQuestion`` list).
Pure-Python: stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

_DEFAULT_THRESHOLD: float = 0.70

# Stop-words stripped before measuring (lexical floor — no stemming/synonymy).
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
class OpenQuestionText:
    """One open question's text. Pure input."""

    node_id: str
    text: str | None


@dataclass(frozen=True)
class RedundantQuestionPair:
    """One flagged near-duplicate question pair. Auditable."""

    question_a_id: str
    question_b_id: str
    similarity: float
    shared_terms: tuple[str, ...]  # sorted distinctive terms in both


@dataclass(frozen=True)
class QuestionRedundancyReport:
    """The question-redundancy verdict. Advisory, pure."""

    measurable_question_count: int
    unmeasurable_count: int
    redundant_pairs: tuple[RedundantQuestionPair, ...]
    implicated_question_ids: tuple[str, ...]
    redundancy_ratio: float | None  # implicated/total; None when unknown
    max_similarity: float | None  # strongest pairwise signal; None when unknown
    threshold: float
    verdict: str  # unknown | redundant | distinct
    notes: tuple[str, ...]
    authority: str = "advisory"


class QuestionRedundancyError(ValueError):
    """A question-redundancy input violates a load-bearing invariant."""


def measure_question_redundancy(
    questions: Sequence[OpenQuestionText],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
) -> QuestionRedundancyReport:
    """Detect near-duplicate open questions within the artifact.

    ``questions`` are the open questions to compare.
    ``threshold`` is the Jaccard similarity at/above which a pair is flagged
    (default 0.70 — strict, catching near-exact paraphrases).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= threshold <= 1.0:
        raise QuestionRedundancyError(
            f"threshold must be in [0,1], got {threshold!r}"
        )

    seen_ids: set[str] = set()
    for q in questions:
        if not q.node_id.strip():
            raise QuestionRedundancyError(
                f"node_id must be non-empty, got {q.node_id!r}"
            )
        if q.node_id in seen_ids:
            raise QuestionRedundancyError(
                f"duplicate node_id {q.node_id!r}"
            )
        seen_ids.add(q.node_id)

    # Tokenize each question to its distinctive-term set; separate all-glue.
    term_sets: list[tuple[str, set[str]]] = []
    unmeasurable = 0
    for q in questions:
        terms = _distinctive_terms(q.text)
        if not terms:
            unmeasurable += 1
        else:
            term_sets.append((q.node_id, terms))

    measurable = len(term_sets)

    # Fewer than two measurable questions -> unknown (defer — a single question
    # cannot be redundant with itself; never fabricated as non-redundant).
    if measurable < 2:
        return _report(
            measurable, unmeasurable, (), (), None, None, threshold, "unknown",
            [
                "question-redundancy detects near-duplicate QUESTIONS (the same "
                "UNKNOWN asked twice); distinct from insight_redundancy #1939 "
                "(near-duplicate INSIGHTS / findings) — questions are UNKNOWNS to "
                "chase, insights are FINDINGS learned; structurally different "
                "objects, different failure modes (dup questions waste RECURSION "
                "budget + dilute question-counting measurements)",
                "verdict unknown — fewer than two measurable questions (defer; a "
                "single question cannot be redundant with itself — redundancy_ratio "
                "and max_similarity are None, never fabricated)",
            ],
        )

    flagged: list[RedundantQuestionPair] = []
    max_similarity = 0.0
    for (id_a, set_a), (id_b, set_b) in combinations(term_sets, 2):
        union = set_a | set_b
        if not union:
            continue
        similarity = len(set_a & set_b) / len(union)
        if similarity > max_similarity:
            max_similarity = similarity
        if similarity >= threshold:
            shared = tuple(sorted(set_a & set_b))
            flagged.append(
                RedundantQuestionPair(
                    question_a_id=id_a,
                    question_b_id=id_b,
                    similarity=similarity,
                    shared_terms=shared,
                )
            )

    implicated: set[str] = set()
    for pair in flagged:
        implicated.add(pair.question_a_id)
        implicated.add(pair.question_b_id)

    redundancy_ratio = len(implicated) / measurable

    verdict = "redundant" if flagged else "distinct"

    notes: list[str] = [
        "question-redundancy detects near-duplicate QUESTIONS (the same UNKNOWN "
        "asked twice in different wording); distinct from insight_redundancy #1939 "
        "(near-duplicate INSIGHTS) — questions are UNKNOWNS, insights are "
        "FINDINGS; dup questions waste RECURSION budget (two chases for one "
        "question) and dilute research_yield #1944 / open_question_closure #1977",
        "for every question pair: Jaccard over distinctive terms (stop-word + "
        "interrogative stripped, NO stemming/synonymy); pairs >= threshold "
        "(default 0.70 — strict, near-exact paraphrases) flagged; redundancy_ratio "
        "= implicated/total in [0,1]; max_similarity carried even when below "
        "threshold (operator sees the highest overlap regardless)",
        "verdict: redundant (>=1 flagged pair), distinct (zero flagged AND "
        "measured — a REAL verdict, not the default), unknown (<2 measurable "
        "questions — defer)",
        "unknown != distinct (never collapsed: unknown = not-enough-to-measure; "
        "distinct = measured-and-clean); all-glue questions excluded (no "
        "distinctive terms = cannot near-duplicate by this measure, carried as "
        "unmeasurable_count); pure + advisory + deterministic",
    ]
    notes.append(
        f"verdict {verdict}: {len(flagged)} redundant pair(s) of "
        f"C({measurable},2) pairs, {len(implicated)} implicated question(s), "
        f"redundancy_ratio {redundancy_ratio:.0%}, max_similarity "
        f"{max_similarity:.2f}, threshold {threshold:.0%}"
    )

    return _report(
        measurable, unmeasurable, tuple(flagged), tuple(sorted(implicated)),
        redundancy_ratio, max_similarity, threshold, verdict, notes,
    )


def _distinctive_terms(text: str | None) -> set[str]:
    """Lexical distinctive-term set for one question (stop-words stripped).

    All-glue text contributes nothing (empty set). Lowercased.
    """
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def _report(
    measurable: int,
    unmeasurable: int,
    redundant_pairs: tuple[RedundantQuestionPair, ...],
    implicated_ids: tuple[str, ...],
    redundancy_ratio: float | None,
    max_similarity: float | None,
    threshold: float,
    verdict: str,
    notes: list[str],
) -> QuestionRedundancyReport:
    return QuestionRedundancyReport(
        measurable_question_count=measurable,
        unmeasurable_count=unmeasurable,
        redundant_pairs=redundant_pairs,
        implicated_question_ids=implicated_ids,
        redundancy_ratio=redundancy_ratio,
        max_similarity=max_similarity,
        threshold=threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
