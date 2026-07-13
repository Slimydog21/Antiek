r"""Citation relevance — does a cited source actually relate to the insight's claim?

Operator vision (asks #1/#7/#14): *"send subagents to chase questions as I
Interrogate, assess, and wrestle with the information"* (ask #1), *"call arxiv,
substack, and other knowledge-dense publications to be referenced"* (ask #7),
*"intelligent search over my dream of an infinite information platform"* (ask #14).
Two axes already touch the citation surface:

* ``provenance_coverage`` (#1940): does the insight CARRY a source id — the
  structural PRESENCE signal (does the ``source_document_id`` field exist?). It
  catches floating claims (insights with no source at all).
* ``provenance/validate_refs.py`` (on main): do the source ids RESOLVE — the
  reference validity signal (do the refs point to real documents?).

NEITHER measures citation QUALITY — when an insight DOES cite a source, is that
source actually RELEVANT to the insight's claim? An insight can carry a valid
source id (passes #1940, passes validate_refs) yet cite an IRRELEVANT source: the
citation is present and resolves, but the source's content shares no subject with
the insight's claim. That is a MISATTRIBUTION — a citation that LOOKS grounded but
is not. The operator's "wrestle with the information" directive demands the
platform surface misattributions: a claim attributed to a source that doesn't
support it undermines the research's intellectual integrity.

**Genuinely distinct (presence vs quality vs validity):**

* ``provenance_coverage`` (#1940): citation PRESENCE (does the field exist?).
* ``validate_refs`` (on main): citation VALIDITY (does the ref resolve?).
* THIS (``citation_relevance``): citation QUALITY (does the cited source's CONTENT
  relate to the insight's claim?).

They are independent and complementary. An insight can pass all three (cites a
relevant, resolving source), pass #1940 + validate_refs but fail THIS (cites an
irrelevant-but-real source — misattribution), or fail #1940 (no citation at all —
the floating claim). PRESENCE catches "no citation"; VALIDITY catches "broken
citation"; QUALITY catches "wrong citation." The misattribution detector is the
missing third layer — without it, a research artifact can look fully sourced
(#1940 high, all refs resolve) while every citation points to the wrong document.

**The measurement (hard to vary).** Given a set of cited insights — each pairing
an insight's text with its cited source's text — for each pair compute the Jaccard
overlap over their distinctive terms (stop-word-stripped, NO stemming/synonymy —
the lexical floor pinned across all text axes): ``|insight ∩ source| / |insight ∪
source|``.

* ``pair_count`` — cited insights measured (those with both insight text and source
  text).
* ``relevance_ratios`` — per-pair Jaccard in ``[0, 1]`` (auditable: both ids + the
  ratio + matched terms).
* ``mean_relevance`` — the average Jaccard across all pairs.
* ``max_relevance`` — the strongest citation (the best-aligned source-claim pair).
* ``misattribution_count`` — pairs where Jaccard < ``relevance_threshold`` (default
  ``0.10`` — a lenient floor: the source must share SOME distinctive vocabulary
  with the claim to not be flagged; a stricter threshold would flag paraphrases,
  but this is a lexical detector that prefers false negatives to false positives —
  a semantic reranker can confirm downstream).
* ``misattribution_rate`` — misattributions / total pairs.

**Verdict (distinct honest states, never collapsed):**

* zero measurable pairs (no cited insights, or insight/source text missing) ->
  ``unknown`` (defer — never fabricated).
* ``misattribution_count == 0`` AND ``pair_count >= 1`` -> ``well_cited`` (every
  citation shares at least the relevance-threshold vocabulary with its claim — a
  REAL measured verdict, distinct from ``unknown``).
* ``misattribution_rate >= majority_threshold`` (default ``0.50``) -> ``misattributed``
  (MOST citations are misattributions — the sourcing is systematically wrong).
* otherwise -> ``partially_misattributed`` (some citations misattributed, some
  sound — the common mixed shape).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero measurable pairs (no cited insights or
  no text to compare — defer).
* ``well_cited`` is a REAL measured verdict (every pair measured and clean), NOT
  the default — ``unknown`` means nothing-to-measure; ``well_cited`` means
  measured-and-clean. Never collapsed.
* ``mean_relevance`` / ``max_relevance`` / ``misattribution_rate`` are ``None``
  when zero pairs (defer — never ``0.0``).
* all-glue text (only stop-words) on either side yields Jaccard ``0.0`` by this
  measure (no distinctive vocabulary to share) — a pair where the insight is
  all-glue is EXCLUDED (carried as ``unmeasurable_pair_count``); a pair where the
  source is all-glue but the insight has terms yields 0.0 (a real signal: the
  source provides no distinctive vocabulary — likely misattributed or empty).
* Distinct from twin_fidelity #1954 (hallucination — does the twin text match the
  source verbatim): THIS is subject overlap, not verbatim matching. A faithful
  twin can cite a relevant source (high relevance, high fidelity); a source can
  be relevant (high relevance) yet the twin can still hallucinate beyond it (low
  fidelity).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``CitedInsight`` input shape
(insight text + cited source text); the route layer adapts 1:1 from the artifact's
insights joined to their cited source documents. Pure-Python: stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_RELEVANCE_THRESHOLD: float = 0.10
_DEFAULT_MAJORITY_THRESHOLD: float = 0.50

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
class CitedInsight:
    """One insight paired with its cited source's text. Pure input.

    ``insight_id`` identifies the insight; ``source_id`` identifies the cited
    source. ``insight_text`` is the insight's claim; ``source_text`` is the cited
    source's content (the route layer joins the insight to its source document).
    """

    insight_id: str
    source_id: str
    insight_text: str | None
    source_text: str | None


@dataclass(frozen=True)
class CitationRelevancePair:
    """One insight-source pair's relevance measurement. Auditable."""

    insight_id: str
    source_id: str
    relevance: float  # Jaccard over distinctive terms, in [0, 1]
    matched_terms: tuple[str, ...]  # sorted distinctive terms in both


@dataclass(frozen=True)
class CitationRelevanceReport:
    """The citation-quality verdict. Advisory, pure."""

    pair_count: int
    unmeasurable_pair_count: int
    misattribution_count: int
    misattribution_rate: float | None  # misattributions / pairs; None when unknown
    mean_relevance: float | None  # average Jaccard; None when unknown
    max_relevance: float | None  # strongest pair; None when unknown
    misattributed_pair_ids: tuple[tuple[str, str], ...]  # (insight_id, source_id)
    pairs: tuple[CitationRelevancePair, ...]  # all measured pairs, sorted
    relevance_threshold: float
    majority_threshold: float
    verdict: str  # well_cited | misattributed | partially_misattributed | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _distinctive_terms(text: str | None) -> frozenset[str]:
    if text is None:
        return frozenset()
    tokens = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in tokens if t not in _STOP_WORDS)


def measure_citation_relevance(
    cited_insights: Sequence[CitedInsight],
    *,
    relevance_threshold: float = _DEFAULT_RELEVANCE_THRESHOLD,
    majority_threshold: float = _DEFAULT_MAJORITY_THRESHOLD,
) -> CitationRelevanceReport:
    r"""Measure whether cited sources are relevant to their insights' claims.

    ``cited_insights`` pairs each insight with its cited source's text. Returns a
    :class:`CitationRelevanceReport` with per-pair Jaccard relevance,
    misattribution detection, and verdict.

    Raises:
        ValueError: if thresholds are outside ``(0, 1]`` or ``relevance_threshold``
            >= ``majority_threshold``.
    """
    if not 0.0 < relevance_threshold <= 1.0:
        raise ValueError(
            f"relevance_threshold must be in (0.0, 1.0]; got {relevance_threshold}"
        )
    if not 0.0 < majority_threshold <= 1.0:
        raise ValueError(
            f"majority_threshold must be in (0.0, 1.0]; got {majority_threshold}"
        )

    measured: list[CitationRelevancePair] = []
    unmeasurable = 0
    misattributed_ids: list[tuple[str, str]] = []

    for ci in cited_insights:
        insight_terms = _distinctive_terms(ci.insight_text)
        source_terms = _distinctive_terms(ci.source_text)
        # Exclude pairs where the INSIGHT has no distinctive terms (all-glue) —
        # no claim to measure relevance against.
        if not insight_terms:
            unmeasurable += 1
            continue
        union = insight_terms | source_terms
        if not union:
            # Both empty — structurally excluded above (insight_terms non-empty).
            unmeasurable += 1
            continue
        intersection = insight_terms & source_terms
        relevance = len(intersection) / len(union)
        measured.append(
            CitationRelevancePair(
                insight_id=ci.insight_id,
                source_id=ci.source_id,
                relevance=relevance,
                matched_terms=tuple(sorted(intersection)),
            )
        )
        if relevance < relevance_threshold:
            misattributed_ids.append((ci.insight_id, ci.source_id))

    pair_count = len(measured)
    if pair_count == 0:
        return CitationRelevanceReport(
            pair_count=0,
            unmeasurable_pair_count=unmeasurable,
            misattribution_count=0,
            misattribution_rate=None,
            mean_relevance=None,
            max_relevance=None,
            misattributed_pair_ids=(),
            pairs=(),
            relevance_threshold=relevance_threshold,
            majority_threshold=majority_threshold,
            verdict="unknown",
            notes=("no measurable cited insights",),
        )

    measured.sort(key=lambda p: (p.insight_id, p.source_id))
    misattributed_ids.sort()

    misattribution_count = len(misattributed_ids)
    misattribution_rate = misattribution_count / pair_count
    relevances = [p.relevance for p in measured]
    mean_relevance = sum(relevances) / pair_count
    max_relevance = max(relevances)

    if misattribution_count == 0:
        verdict = "well_cited"
    elif misattribution_rate >= majority_threshold:
        verdict = "misattributed"
    else:
        verdict = "partially_misattributed"

    notes = (
        f"{misattribution_count} of {pair_count} citation(s) misattributed "
        f"(rate {misattribution_rate:.4f}); mean relevance {mean_relevance:.4f}",
    )

    return CitationRelevanceReport(
        pair_count=pair_count,
        unmeasurable_pair_count=unmeasurable,
        misattribution_count=misattribution_count,
        misattribution_rate=misattribution_rate,
        mean_relevance=mean_relevance,
        max_relevance=max_relevance,
        misattributed_pair_ids=tuple(misattributed_ids),
        pairs=tuple(measured),
        relevance_threshold=relevance_threshold,
        majority_threshold=majority_threshold,
        verdict=verdict,
        notes=notes,
    )
