"""Artifact-level contradiction — do the insights conflict with each other?

Operator vision (ask #1): *"interrogate, assess, and wrestle with the
information in front of me."* When artifacts are MERGED — collective synthesis
(#1835), twin merge (#1852), MO promote (#1899) — the result combines insights
from DIFFERENT sources. Two sources can genuinely CONTRADICT: one says *"the
model scales well"* and another says *"the model does not scale."* A human
reading the merged artifact needs to SEE the contradictions to wrestle with them
— an artifact that silently carries both sides of a conflict without surfacing
it is not a tool for interrogation, it is a conflict-hider.

THIS module finds contradiction pairs INSIDE one artifact — the surface where the
operator's stated *"wrestle with the information"* begins.

**Distinct from ``redundancy`` (#1939).** That finds near-duplicate AGREEMENT —
two insights that say the same thing (high Jaccard, no conflict). This finds
near-duplicate SUBJECT with CONFLICT — two insights about the same thing that
disagree (high Jaccard AND asymmetric negation). They are opposite failure modes:
redundancy = said twice (agreeing), contradiction = said twice (conflicting).
Both are unique to merged output.

**Distinct from the graph-level ``gap_detection.contradiction``.** That module
operates over the WHOLE GRAPH via a DB connection + embedding cosine similarity
(≥ 0.85) + an injected verifier. It needs a live DB and precomputed embeddings.
THIS module operates purely on ONE artifact's insight TEXTS — no DB, no embeddings,
no network. The graph detector is the production-wide scan; this is the per-
artifact surface a human reviews when reading one research output. They share the
proven ``negation_verifier`` heuristic (consistency with the codebase): a pair
conflicts iff exactly one of the two insights carries a negation marker.

**The two-stage precision design (hard to vary).** A contradiction requires BOTH:
  1. **Same subject** — the pair's distinctive-term Jaccard ≥ ``subject_threshold``
     (default 0.30 — lower than redundancy's 0.70, because a conflict can be over
     a narrow shared subject; the negation verifier supplies the precision the
     looser gate would otherwise lose). Two insights about unrelated things cannot
     contradict, no matter their negation.
  2. **Asymmetric negation** — exactly one of the two carries a negation marker
     (``not``/``no``/``never``/``cannot``/``fails``/``without``/``lacks``...).
     This is the high-precision, low-recall stance documented in
     ``gap_detection.contradiction``: *"a detector that cries wolf is worse than
     none."* We would rather miss a real contradiction than flood the operator's
     queue with false ones.

**Honest scope (load-bearing).** This is a LEXICAL floor, not semantic
contradiction detection — the same discipline as the other axes. A pair that
genuinely conflicts via subtle phrasing (no negation marker, e.g. *"thrive"* vs
*"struggle"*) is NOT flagged; catching that needs an LLM judge (out of scope). The
negation set is documented and mirrors ``gap_detection.contradiction``: if that
set changes, the drift is visible (both must agree on what counts as a negation).

**Honesty rules (load-bearing):**
* An artifact with fewer than two insights has ``max_subject_overlap = None``
  (never fabricated 0) — a single insight cannot contradict itself here.
* Two insights with NO shared distinctive terms cannot contradict (Jaccard 0 <
  threshold) — surfaced as zero contradictions, not a false clean.
* ``contradiction_ratio`` is ``contradicting_insight_ids / insight_count`` (0.0
  when there are no insights) — the share of the artifact implicated in a
  contradiction.
* Every contradiction pair is auditable: both node_ids, the Jaccard, the shared
  subject terms, and which side carries the negation.
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation, no DB. ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody


class ContradictionError(ValueError):
    """A contradiction-detection input violates a load-bearing invariant."""
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Negation markers — mirrors gap_detection.contradaction so both agree on what
# counts as a conflict signal. If that set changes, update here too (documented
# mirror).
_NEGATION_RE = re.compile(
    r"\b(not|no|never|cannot|can't|isn't|aren't|doesn't|don't|won't|wouldn't|"
    r"shouldn't|couldn't|fails?|failed|without|lacks?|unable|unable to|"
    r"prevent|prevents|denies|rejected|refuse|refuses)\b",
    re.IGNORECASE,
)

# Stop-words stripped so Jaccard measures subject-word overlap, not grammar.
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

_DEFAULT_SUBJECT_THRESHOLD: float = 0.30


@dataclass(frozen=True)
class ContradictionPair:
    """One conflicting insight pair. Auditable."""

    node_id_a: str
    node_id_b: str
    subject_overlap: float  # Jaccard over distinctive terms in [0,1]
    shared_subject_terms: tuple[str, ...]  # sorted distinctive terms shared
    negated_side: str  # "a" | "b" — which insight carries the negation


@dataclass(frozen=True)
class ContradictionReport:
    """The artifact's internal-contradiction surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    insight_count: int
    pair_count: int  # insight pairs compared (n choose 2)
    contradiction_pairs: tuple[ContradictionPair, ...]  # sorted desc by overlap
    contradicting_insight_ids: tuple[str, ...]  # unique node_ids in ANY pair
    contradiction_ratio: float  # contradicting_insight_ids / insight_count; 0.0 if none
    max_subject_overlap: float | None  # highest Jaccard over ALL pairs; None if <2
    subject_threshold: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _distinctive_terms(text: str) -> set[str]:
    return {tok for tok in _tokenize(text) if tok not in _STOP_WORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_negated(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def detect_contradictions(
    artifact: ResearchArtifactBody,
    *,
    subject_threshold: float = _DEFAULT_SUBJECT_THRESHOLD,
) -> ContradictionReport:
    """Find insight pairs that conflict (same subject + asymmetric negation).

    ``artifact`` is the canonical knowledge-asset body. ``subject_threshold`` is
    the minimum distinctive-term Jaccard for two insights to be considered
    "about the same thing" (default 0.30). Returns a :class:`ContradictionReport`
    with the contradiction pairs and the implicated-insight accountability surface.

    Pure: no DB, no embeddings, no LLM, no clock, no mutation.
    """
    if not 0.0 < subject_threshold <= 1.0:
        raise ContradictionError(
            f"subject_threshold must be in (0.0, 1.0], got {subject_threshold!r}"
        )

    insights = artifact.insights
    n = len(insights)
    pair_count = n * (n - 1) // 2

    term_sets = [_distinctive_terms(ins.text) for ins in insights]
    negated = [_is_negated(ins.text) for ins in insights]

    contradictions: list[ContradictionPair] = []
    best: float | None = None

    for i in range(n):
        for j in range(i + 1, n):
            overlap = _jaccard(term_sets[i], term_sets[j])
            if best is None or overlap > best:
                best = overlap
            # Contradiction requires BOTH: same subject (overlap >= threshold)
            # AND asymmetric negation (exactly one negated).
            if overlap >= subject_threshold and negated[i] != negated[j]:
                shared = tuple(sorted(term_sets[i] & term_sets[j]))
                contradictions.append(
                    ContradictionPair(
                        node_id_a=insights[i].node_id,
                        node_id_b=insights[j].node_id,
                        subject_overlap=overlap,
                        shared_subject_terms=shared,
                        negated_side="a" if negated[i] else "b",
                    )
                )

    contradictions.sort(
        key=lambda p: (-p.subject_overlap, p.node_id_a, p.node_id_b)
    )
    contradiction_pairs = tuple(contradictions)

    implicated = sorted(
        {pid for pair in contradiction_pairs for pid in (pair.node_id_a, pair.node_id_b)}
    )
    ratio = (len(implicated) / n) if n else 0.0

    notes: list[str] = [
        "contradiction detection is a LEXICAL floor (same-subject Jaccard + "
        "asymmetric negation); subtle conflicts without a negation marker are "
        "not flagged; semantic contradiction detection is an LLM-judge concern, "
        "out of scope",
        "the negation set mirrors gap_detection.contradiction so both agree on "
        "what counts as a conflict signal",
    ]
    if n < 2:
        notes.append(
            f"only {n} insight(s); internal contradiction is not measurable "
            "(needs at least two insights to conflict)"
        )
    else:
        notes.append(
            f"compared {pair_count} insight pair(s) at subject threshold "
            f"{subject_threshold:.2f}; {len(contradiction_pairs)} contradiction "
            f"pair(s) implicating {len(implicated)} of {n} insight(s) "
            f"(contradiction ratio {ratio:.0%})"
        )
        if contradiction_pairs:
            notes.append(
                f"WRESTLE: {len(contradiction_pairs)} pair(s) conflict — the "
                "operator should interrogate these before trusting the synthesis"
            )
        if best is not None:
            tag = " (below subject threshold)" if best < subject_threshold else ""
            notes.append(f"highest pair subject-overlap was {best:.2f}{tag}")

    return ContradictionReport(
        artifact_id=artifact.investigation_id,
        insight_count=n,
        pair_count=pair_count,
        contradiction_pairs=contradiction_pairs,
        contradicting_insight_ids=tuple(implicated),
        contradiction_ratio=ratio,
        max_subject_overlap=best,
        subject_threshold=subject_threshold,
        notes=tuple(notes),
    )
__all__ = [
    "ContradictionError",
    "ContradictionPair",
    "ContradictionReport",
    "detect_contradictions",
]
