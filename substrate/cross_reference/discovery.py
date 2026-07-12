"""Cross-reference discovery — how a focus finding connects to prior work.

Operator vision (ask #4): the twin substrate of insights and questions *"can be
merged, referenced, and leveraged in combining contexts or doing intelligent
search over my dream of an infinite information platform."* Three of those four
verbs are built: MERGED (#1833/#1835/#1837), LEVERAGED-in-combining-contexts
(#1845 context assembly), SEARCHED (#1844/#789). The missing verb is
**REFERENCED** — the connective tissue that makes the platform COMPOUND. As
investigations accumulate, the operator needs to see how a new finding connects
to prior findings: *"you found X in investigation A; it shares its subject with
insight Y from investigation B."* Without that, each artifact is an island; the
substrate never becomes a knowledge graph.

THIS module is the pure cross-reference discovery layer.

**Distinct from redundancy (#1939).** That finds near-duplicate AGREEMENT
WITHIN one artifact (insight X repeats insight Y). This finds subject-overlap
ACROSS artifacts (focus insight Z connects to prior insight W). Different scope
(cross-artifact, not within), different purpose (navigation/linking, not
deduplication).

**Distinct from contradiction (#1943).** That finds within-artifact conflicts
(same-subject + asymmetric negation). This finds cross-artifact subject-overlap
WITHOUT classifying the relationship — a connection may be agreement,
disagreement, or elaboration; the operator determines the nature. This module
surfaces the CONNECTION (shared subject); it does not judge the polarity.

**Distinct from search (#1844).** That answers a free-form query against stored
chunks (one-directional retrieval). This is automatic link-discovery FROM a
focus artifact's own findings (no query — the focus IS the query).

**The connection (hard to vary).** Two insights cross-reference when they share
DISTINCTIVE subject terms above a floor. ``overlap_score`` is the Jaccard index
over the two insights' distinctive-term sets: ``|A ∩ B| / |A ∪ B|`` in ``[0, 1]``.
``1.0`` = identical subject vocabulary; ``0.0`` = no shared distinctive terms.
A cross-reference requires ``overlap_score >= min_overlap`` (default ``0.30``,
the same high-precision low-recall floor the contradiction axis uses — a
detector that cries wolf erodes trust faster than one that misses a paraphrase).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are the
content words (everything that is not grammatical glue: articles, prepositions,
conjunctions, pronouns, auxiliaries). There is NO stemming and NO synonymy:
``model`` and ``models`` are distinct terms; ``LLM`` and ``language model`` are
unrelated. This is deliberate — stemming/synonymy would mask real signals
behind phony matches (``effective`` and ``efficient`` are NOT the same finding).
The cost is low recall (a paraphrased connection is missed); the benefit is
high precision (every surfaced connection has auditable shared terms). The
operator can always widen with semantic re-rank (#1844) downstream.

**Honest scope (load-bearing).** This is a STRUCTURAL subject-overlap detector,
not a semantic relationship classifier. It does NOT assert that a cross-
reference means agreement, contradiction, or elaboration — it asserts only that
two insights share subject matter. The shared_terms tuple is the AUDITABLE
evidence (the operator sees exactly WHY the connection was surfaced). It does
NOT prescribe action — surfacing is advisory; merging/contradicting is the
operator's call.

**Honesty rules (load-bearing):**
* An artifact never cross-references ITSELF. Priors sharing the focus's
  ``investigation_id`` are skipped (within-artifact linking is redundancy
  #1939's job, not this module's).
* Empty focus insights OR empty priors -> empty ``cross_references`` (no
  fabricated connections — the defer, never a hallucinated link).
* Duplicate prior investigation_ids are de-duplicated (keep first); the report
  counts DISTINCT prior investigations examined.
* ``overlap_score`` is in ``[0.0, 1.0]``; ``shared_terms`` is non-empty for every
  surfaced cross-reference (a link with no shared evidence is never emitted).
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

# Grammatical glue only — articles, prepositions, conjunctions, pronouns,
# auxiliaries, particles. Deliberately EXCLUDES content words: "present",
# "effective", "stable", "principles", "model", "research" etc. are all
# DISTINCTIVE (kept) so they carry real subject signal. Stop-word stripping
# applies to BOTH focus and prior sides so grammatical glue never inflates the
# Jaccard numerator.
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
        tok
        for tok in _WORD_RE.findall(text.lower())
        if tok not in _STOP_WORDS
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|A ∩ B| / |A ∪ B| in [0, 1]; 0.0 when the union is empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class CrossReferenceError(ValueError):
    """A cross-reference input violates a load-bearing invariant."""


@dataclass(frozen=True)
class InsightCrossReference:
    """One focus insight connected to one prior insight by shared subject."""

    focus_insight_node_id: str
    focus_insight_text: str
    prior_investigation_id: str
    prior_insight_node_id: str
    prior_insight_text: str
    shared_terms: tuple[str, ...]  # distinctive terms both share (auditable evidence)
    overlap_score: float  # Jaccard over distinctive-term sets, in [0.0, 1.0]


@dataclass(frozen=True)
class CrossReferenceReport:
    """The focus artifact's connections to prior work. Advisory, pure."""

    focus_investigation_id: str
    cross_references: tuple[InsightCrossReference, ...]  # sorted: overlap desc, then ids
    prior_investigation_count: int  # distinct priors examined
    connected_prior_count: int  # distinct priors with >= 1 cross-reference
    min_overlap: float
    authority: str = "advisory"


def discover_cross_references(
    focus: ResearchArtifactBody,
    priors: Sequence[ResearchArtifactBody],
    *,
    min_overlap: float = _DEFAULT_MIN_OVERLAP,
) -> CrossReferenceReport:
    """Discover how the focus artifact's insights connect to prior work.

    ``focus`` is the artifact the operator is engaging with now; ``priors`` are
    completed investigations to cross-reference against. Returns a
    :class:`CrossReferenceReport` with the subject-overlap connections, sorted by
    strength. Pure: no DB, no LLM, no clock, no mutation.

    Priors sharing the focus's ``investigation_id`` are skipped (an artifact
    never cross-references itself; within-artifact linking is redundancy #1939).
    Duplicate prior investigation_ids are de-duplicated (keep first).
    """
    if not 0.0 < min_overlap <= 1.0:
        raise CrossReferenceError(
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

    # Pre-compute distinctive-term sets once per insight (avoid recomputation).
    focus_terms = [
        (ins.node_id, ins.text, _distinctive_terms(ins.text))
        for ins in focus.insights
    ]
    prior_terms: list[tuple[str, str, str, frozenset[str]]] = [
        (p.investigation_id, ins.node_id, ins.text, _distinctive_terms(ins.text))
        for p in distinct_priors
        for ins in p.insights
    ]

    refs: list[InsightCrossReference] = []
    for f_id, f_text, f_set in focus_terms:
        if not f_set:
            continue  # an insight with no distinctive terms cannot connect
        for p_inv, p_id, p_text, p_set in prior_terms:
            if not p_set:
                continue
            score = _jaccard(f_set, p_set)
            if score >= min_overlap:
                shared = tuple(sorted(f_set & p_set))
                refs.append(
                    InsightCrossReference(
                        focus_insight_node_id=f_id,
                        focus_insight_text=f_text,
                        prior_investigation_id=p_inv,
                        prior_insight_node_id=p_id,
                        prior_insight_text=p_text,
                        shared_terms=shared,
                        overlap_score=score,
                    )
                )

    # Deterministic sort: strongest first, then by node ids for stable order.
    refs.sort(
        key=lambda r: (-r.overlap_score, r.focus_insight_node_id, r.prior_investigation_id, r.prior_insight_node_id)
    )
    connected_priors = {r.prior_investigation_id for r in refs}

    return CrossReferenceReport(
        focus_investigation_id=focus.investigation_id,
        cross_references=tuple(refs),
        prior_investigation_count=len(distinct_priors),
        connected_prior_count=len(connected_priors),
        min_overlap=min_overlap,
    )


__all__ = [
    "CrossReferenceError",
    "CrossReferenceReport",
    "InsightCrossReference",
    "discover_cross_references",
]
