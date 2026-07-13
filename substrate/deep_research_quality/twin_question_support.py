"""Twin question support — are the twin's open questions grounded in the source?

Operator vision (ask #4): *"every information asset ... has a twin document with
all the insights and questions proposed by that information document written by an
LLM."* The twin's open questions are the RECURSIVE ENGINE'S FUEL — each one is a
candidate sub-investigation that sends a subagent chasing an answer. A fabricated
question the source never raised sends the subagent chasing a PHANTOM: it spawns a
new investigation grounded in nothing, pollutes the knowledge graph with a dead
branch, and wastes the operator's budget. The operator's "infinite information
platform" is only trustworthy if its recursive questions are grounded.

No current axis measures this. ``twin_fidelity`` (#1954) measures whether the
twin's INSIGHTS are lexically supported by the source text — it does NOT cover
``open_questions`` (the twin's questions are a separate field, not measured there).
``citation_grounding`` (#1848) checks structural provenance on insights, not
question grounding. ``problem_question_coverage`` (#1929) checks whether the
artifact answers ITS OWN question. THIS is the missing check: does each twin open
question have term overlap with the source it was generated from?

**The measurement (hard to vary).** For each twin open question:

* Extract its distinctive terms (content words, glue stripped — the shared lexical
  floor of all quality/cross-reference modules).
* Compute ``support_ratio = |question_terms ∩ source_terms| / |question_terms|`` —
  the fraction of the question's distinctive vocabulary present in the source.
* A question with ``support_ratio >= support_threshold`` (default 0.50) is
  ``supported`` (grounded in the source); below is ``unsupported`` (the twin
  invented a question the source doesn't underwrite — a phantom-chase signal).
* Questions with no distinctive terms are ``unmeasurable`` (excluded from the rate,
  never fabricated — e.g. "why?" alone is all-glue).

The module reports:

* ``supported_count`` / ``unsupported_count`` / ``unmeasurable_count``.
* ``question_support_rate = supported / measurable`` (``None`` when zero measurable).
* per-question ``QuestionSupport`` (``node_id``, ``support_ratio``, ``verdict``,
  ``unsupported_terms`` — the auditable evidence: exactly which terms the source
  lacks).
* ``escalated_unsupported_count`` — the dangerous subset: unsupported questions
  that are ALSO escalated (flagged for subagent chase). These are the highest-risk
    phantom branches. Carried separately so the operator sees the acute risk.

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content words
(glue stripped), NO stemming, NO synonymy. A paraphrased question (same meaning,
different words) may score low — that is the precision/recall tradeoff, the SAME
direction as twin_fidelity (#1954): this detector prefers flagging a paraphrase
(false positive) over certifying a phantom question as grounded (false negative). A
phantom question accepted as "supported" spawns a dead investigation branch; a
paraphrase flagged as "unsupported" is a minor inconvenience the operator confirms
downstream. The conservative error is the safe one.

**Honesty rules (load-bearing):**

* A question with NO distinctive terms (empty or all-glue) is ``unmeasurable`` —
  excluded from the rate, carried through as a count (never fabricated).
* ``question_support_rate`` is ``None`` when zero measurable questions (defer —
  never ``0.0`` or ``1.0``).
* The source text's own distinctive terms are the ground truth — if the source is
  empty or all-glue, every question is ``unmeasurable``.
* ``support_ratio`` is in ``[0.0, 1.0]``; ``unsupported_terms`` is the set
  difference (auditable).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock,
  no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The source
text is a plain ``str`` input (the route layer reads it from the asset store).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_SUPPORT_THRESHOLD: float = 0.50

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


class TwinQuestionSupportError(ValueError):
    """A twin-question-support input violates a load-bearing invariant."""


@dataclass(frozen=True)
class QuestionSupport:
    """One twin open question's support against the source text."""

    node_id: str
    support_ratio: float | None  # None if unmeasurable
    verdict: str  # supported | unsupported | unmeasurable
    unsupported_terms: tuple[str, ...]  # terms missing from source (auditable)
    escalated: bool  # is this question flagged for subagent chase?


@dataclass(frozen=True)
class TwinQuestionSupportReport:
    """The twin's question-grounding profile. Advisory, pure."""

    artifact_id: str
    supported_count: int
    unsupported_count: int
    unmeasurable_count: int
    question_support_rate: float | None  # supported/measurable; None if zero measurable
    escalated_unsupported_count: int  # the acute phantom-chase risk subset
    question_supports: tuple[QuestionSupport, ...]
    support_threshold: float
    verdict: str  # grounded | mixed | ungrounded | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_twin_question_support(
    twin: ResearchArtifactBody,
    source_text: str,
    *,
    support_threshold: float = _DEFAULT_SUPPORT_THRESHOLD,
) -> TwinQuestionSupportReport:
    """Measure whether the twin's open questions are grounded in the source.

    ``twin`` is the LLM-generated twin (a ``ResearchArtifactBody``).
    ``source_text`` is the content the twin was generated from. Returns a
    :class:`TwinQuestionSupportReport` with per-question grounding + the overall
    support rate.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= support_threshold <= 1.0:
        raise TwinQuestionSupportError(
            f"support_threshold must be in [0,1], got {support_threshold!r}"
        )

    source_terms = _distinctive_terms(source_text)

    per_question: list[QuestionSupport] = []
    supported = 0
    unsupported = 0
    unmeasurable = 0
    escalated_unsupported = 0

    for q in twin.open_questions:
        q_terms = _distinctive_terms(q.text)
        if not q_terms or not source_terms:
            per_question.append(
                QuestionSupport(
                    node_id=q.node_id,
                    support_ratio=None,
                    verdict="unmeasurable",
                    unsupported_terms=(),
                    escalated=q.escalated,
                )
            )
            unmeasurable += 1
            continue

        overlap = q_terms & source_terms
        ratio = len(overlap) / len(q_terms)
        missing = tuple(sorted(q_terms - source_terms))

        if ratio >= support_threshold:
            verdict = "supported"
            supported += 1
        else:
            verdict = "unsupported"
            unsupported += 1
            if q.escalated:
                escalated_unsupported += 1

        per_question.append(
            QuestionSupport(
                node_id=q.node_id,
                support_ratio=ratio,
                verdict=verdict,
                unsupported_terms=missing,
                escalated=q.escalated,
            )
        )

    measurable = supported + unsupported
    support_rate = supported / measurable if measurable else None

    if support_rate is None:
        artifact_verdict = "unknown"
    elif support_rate >= 0.70:
        artifact_verdict = "grounded"
    elif support_rate >= 0.40:
        artifact_verdict = "mixed"
    else:
        artifact_verdict = "ungrounded"

    notes: list[str] = [
        "twin question support measures whether the twin's OPEN QUESTIONS are "
        "lexically grounded in the source — a fabricated question sends a subagent "
        "chasing a phantom, spawning a dead investigation branch that pollutes the "
        "knowledge graph and wastes budget; twin_fidelity #1954 checks twin INSIGHTS, "
        "not questions",
        "support_ratio = overlap(question_terms, source_terms) / len(question_terms); "
        ">= threshold supported, below unsupported (phantom-chase signal), no-distinctive-"
        "terms = unmeasurable (excluded from rate, never fabricated); unsupported_terms "
        "is the auditable evidence",
        "escalated_unsupported_count is the acute risk subset: questions BOTH "
        "unsupported AND escalated for subagent chase — these are the highest-probability "
        "phantom branches",
        "lexical floor (no stemming/synonymy): a paraphrased question may score low — "
        "this detector prefers flagging a paraphrase (false positive) over certifying a "
        "phantom as grounded (false negative); a semantic check confirms downstream",
    ]
    if measurable == 0:
        notes.append(
            "no measurable questions (empty twin questions or all-glue/source-empty); "
            "question support is not measurable (defer — never fabricated)"
        )
    else:
        notes.append(
            f"question support rate {support_rate:.0%}: {supported} supported, "
            f"{unsupported} unsupported ({escalated_unsupported} escalated-unsupported), "
            f"{unmeasurable} unmeasurable of {len(twin.open_questions)} twin question(s) "
            f"at threshold {support_threshold:.0%} -> verdict {artifact_verdict}"
        )

    return TwinQuestionSupportReport(
        artifact_id=twin.investigation_id,
        supported_count=supported,
        unsupported_count=unsupported,
        unmeasurable_count=unmeasurable,
        question_support_rate=support_rate,
        escalated_unsupported_count=escalated_unsupported,
        question_supports=tuple(per_question),
        support_threshold=support_threshold,
        verdict=artifact_verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "QuestionSupport",
    "TwinQuestionSupportError",
    "TwinQuestionSupportReport",
    "measure_twin_question_support",
]
