"""Resolution-candidate discovery — does a new finding answer an old question?

Operator vision (ask #4): the workstation *"records the valuable data, insights,
and questions recursively that informs all prompts."* Insights and open questions
are co-equal first-class entities in the canonical ``ResearchArtifactBody``.
Insight↔insight cross-references (#1945) surface how findings CONNECT by subject.
But the highest-value recursive signal is different: **a new finding that may
resolve a PRIOR open question.** When investigation B produces an insight whose
subject overlaps an open question left by investigation A, the platform should
surface *"your new finding is a candidate answer to this previously-open
question"* — the recursive payoff that makes research compound. Without it, open
questions accumulate forever even after their answers have been found.

THIS module is the cross-artifact resolution-candidate discovery layer.

**Candidate, not confirmed (the honesty keystone).** A focus insight that shares
distinctive subject terms with a prior open question is a RESOLUTION CANDIDATE —
it deserves the operator's attention as potentially answering the question. It is
NOT a confirmed resolution: subject-overlap means the finding is ABOUT the
question's topic, not that it ANSWERS it. A finding can share every distinctive
term with a question yet fail to resolve it (it restates the problem; it
addresses a tangent; it is the wrong framing). Confirming resolution is the
operator's judgment (or a follow-up LLM check); this module SURFACES the
candidate with auditable shared_terms evidence and lets the operator decide.

**Distinct from cross-reference discovery (#1945).** That finds insight↔insight
subject SIMILARITY (two findings about the same topic). This finds insight→
question subject-overlap (a finding that may resolve an open question). Different
endpoint types (insight↔insight vs insight→question), different value (navigation
vs resolution-candidate).

**Distinct from problem_question_coverage (#1929).** That asks whether ONE
artifact's output answers ITS OWN problem_question (intra-artifact drift). This
connects a NEW artifact's insights to OTHER artifacts' open questions
(cross-artifact resolution-candidate).

**Distinct from plan_resolution (#1937).** That checks whether a plan's
sub-questions were resolved against a resolved-set (plan execution fidelity). This
surfaces NEW cross-artifact candidates the plan never anticipated.

**Distinct from goal_delivery (#1938).** That measures whether findings address
the operator's frozen GOALS (multi-goal content fidelity). This connects findings
to prior open QUESTIONS (the research graph's unresolved nodes).

**The signal (hard to vary).** ``overlap_score`` is the Jaccard index over the
focus insight's and the prior question's distinctive-term sets:
``|A ∩ B| / |A ∪ B|`` in ``[0, 1]``. A candidate requires ``overlap_score >=
min_overlap`` (default ``0.30``, the same high-precision low-recall floor the
sibling substrates use — surfacing a false candidate erodes trust).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content
words (grammatical glue stripped). NO stemming, NO synonymy: ``model`` and
``models`` are distinct terms. High precision, low recall — the operator can
widen with semantic re-rank downstream.

**Escalated questions are still open questions.** Escalation is a scheduling flag
(see research_yield #1944), not a resolution. A question escalated to a child
investigation but still unresolved is still a valid resolution target — a new
finding may resolve it. Escalated questions are NOT excluded.

**Honesty rules (load-bearing):**
* Empty focus insights OR empty priors OR no prior open questions -> empty
  ``candidates`` (no fabricated resolutions).
* An artifact never resolves its OWN questions (priors sharing the focus's
  ``investigation_id`` are skipped — intra-artifact coverage is #1929's job).
* Duplicate prior investigation_ids are de-duplicated (keep first).
* ``overlap_score`` is in ``[0.0, 1.0]``; ``shared_terms`` is non-empty for every
  candidate (a candidate with no shared evidence is never emitted).
* Deterministic and pure: same inputs -> same report, sorted by overlap desc
  then node ids. No LLM, no network, no clock, no mutation.
* ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_MIN_OVERLAP: float = 0.30

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
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "such", "there", "here", "now",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (grammatical glue stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|A ∩ B| / |A ∪ B| in [0, 1]; 0.0 when the union is empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class ResolutionCandidateError(ValueError):
    """A resolution-candidate input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ResolutionCandidate:
    """A focus insight that may resolve a prior open question (candidate)."""

    focus_insight_node_id: str
    focus_insight_text: str
    prior_investigation_id: str
    prior_question_node_id: str
    prior_question_text: str
    escalated: bool  # was the prior question escalated? (still a valid target)
    shared_terms: tuple[str, ...]  # distinctive terms both share (auditable evidence)
    overlap_score: float  # Jaccard over distinctive-term sets, in [0.0, 1.0]


@dataclass(frozen=True)
class ResolutionCandidateReport:
    """The focus artifact's resolution candidates against prior open questions."""

    focus_investigation_id: str
    candidates: tuple[ResolutionCandidate, ...]  # sorted: overlap desc, then ids
    prior_investigation_count: int  # distinct priors examined
    prior_open_question_count: int  # total open questions across examined priors
    connected_prior_count: int  # distinct priors with >= 1 candidate
    min_overlap: float
    authority: str = "advisory"


def discover_resolution_candidates(
    focus: ResearchArtifactBody,
    priors: Sequence[ResearchArtifactBody],
    *,
    min_overlap: float = _DEFAULT_MIN_OVERLAP,
) -> ResolutionCandidateReport:
    """Discover focus insights that may resolve prior open questions.

    ``focus`` is the artifact whose insights are new findings; ``priors`` are
    completed investigations whose OPEN QUESTIONS are candidate resolution
    targets. Returns a :class:`ResolutionCandidateReport` with the subject-overlap
    candidates, sorted by strength.

    Every candidate is a CANDIDATE, never a confirmed resolution — subject-overlap
    surfaces attention, the operator (or a follow-up check) confirms. Escalated
    questions are valid targets (escalation is scheduling, not resolution).

    Pure: no DB, no LLM, no clock, no mutation. Priors sharing the focus's
    ``investigation_id`` are skipped; duplicate prior ids are de-duplicated.
    """
    if not 0.0 < min_overlap <= 1.0:
        raise ResolutionCandidateError(
            f"min_overlap must be in (0.0, 1.0], got {min_overlap!r}"
        )

    # De-duplicate priors by investigation_id, and skip the focus itself.
    seen_ids: set[str] = set()
    distinct_priors: list[ResearchArtifactBody] = []
    for prior in priors:
        if prior.investigation_id == focus.investigation_id:
            continue
        if prior.investigation_id in seen_ids:
            continue
        seen_ids.add(prior.investigation_id)
        distinct_priors.append(prior)

    focus_terms = [
        (ins.node_id, ins.text, _distinctive_terms(ins.text))
        for ins in focus.insights
    ]
    # Flatten prior open questions with their provenance + escalation flag.
    prior_questions: list[tuple[str, str, str, bool, frozenset[str]]] = [
        (
            p.investigation_id,
            q.node_id,
            q.text,
            q.escalated,
            _distinctive_terms(q.text),
        )
        for p in distinct_priors
        for q in p.open_questions
    ]

    candidates: list[ResolutionCandidate] = []
    for f_id, f_text, f_set in focus_terms:
        if not f_set:
            continue
        for p_inv, q_id, q_text, escalated, q_set in prior_questions:
            if not q_set:
                continue
            score = _jaccard(f_set, q_set)
            if score >= min_overlap:
                shared = tuple(sorted(f_set & q_set))
                candidates.append(
                    ResolutionCandidate(
                        focus_insight_node_id=f_id,
                        focus_insight_text=f_text,
                        prior_investigation_id=p_inv,
                        prior_question_node_id=q_id,
                        prior_question_text=q_text,
                        escalated=escalated,
                        shared_terms=shared,
                        overlap_score=score,
                    )
                )

    candidates.sort(
        key=lambda c: (
            -c.overlap_score,
            c.focus_insight_node_id,
            c.prior_investigation_id,
            c.prior_question_node_id,
        )
    )
    connected_priors = {c.prior_investigation_id for c in candidates}

    return ResolutionCandidateReport(
        focus_investigation_id=focus.investigation_id,
        candidates=tuple(candidates),
        prior_investigation_count=len(distinct_priors),
        prior_open_question_count=len(prior_questions),
        connected_prior_count=len(connected_priors),
        min_overlap=min_overlap,
    )


__all__ = [
    "ResolutionCandidate",
    "ResolutionCandidateError",
    "ResolutionCandidateReport",
    "discover_resolution_candidates",
]
