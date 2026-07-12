"""Search quality — is the ranking any good? (intelligent search, ask #14)

Operator vision: *"that substrate of information can be merged, referenced, and
leveraged in ... intelligent search over my dream of an infinite information
platform"* (ask #14). The platform has many retrieval MECHANISMS — twin-substrate
search (#1844), recursive-twin intelligent search (#894), cross-asset search
(#1037) — but NONE of them is SCORED. A search that cannot be measured cannot be
improved: the operator cannot know whether the ranking puts query-relevant content
first or buries it under noise. And the recursive benchmark (ask #11) has nothing
to optimize search against — search quality is the missing measurement surface.

No current axis measures retrieval quality. The 20 ``deep_research_quality`` axes
all score an ARTIFACT's quality (citation, provenance, diversity, specificity,
authority, twin fidelity, ...). They say nothing about whether a RANKED LIST of
results puts the right things first. cross_reference (#1945) surfaces connections
between artifacts; it does not score a query's ranked output. THIS is that axis:
given a query and a ranked result list, how good is the ranking?

**The measurement (hard to vary).** Lexical relevance over the shared distinctive-
term floor (content words, glue stripped — the same floor as cross_reference and
the other axes):

* For each ranked result at position ``i`` (0-indexed):
  ``relevance_i = |result_terms ∩ query_terms| / |query_terms|`` — the fraction of
  the query's distinctive vocabulary that the result covers (recall-oriented: a
  result addressing every query term is maximally relevant, regardless of length).
  Always in ``[0.0, 1.0]``.
* Rank-discounted cumulative gain (NDCG) — the standard, hard-to-vary ranking
  metric. ``DCG = Σ relevance_i / log2(i + 2)`` (the discount makes top positions
  count more — a relevant result at rank 0 is worth more than at rank 9).
* ``IDCG`` = the DCG of the relevance scores sorted in descending order (the BEST
  possible ranking of the same results). ``NDCG = DCG / IDCG`` normalizes to
  ``[0.0, 1.0]``: ``1.0`` = the ranking is optimal (most relevant first); ``0.0`` =
  no result matches the query at all.

The module reports:

* ``ndcg`` — the rank-discounted quality (``None`` when ``IDCG`` is 0, i.e. every
  result is irrelevant — defer, never ``0.0``).
* ``top_relevance`` — ``relevance_0``, the relevance of the FIRST result (the
  "did the top hit match?" signal; ``None`` when no results).
* ``mean_relevance`` — average relevance across the ranked list.
* ``result_relevances`` — per-position ``ResultRankRelevance`` (``position``,
  ``relevance``, ``matched_query_terms`` — the auditable evidence).
* ``query_term_count`` — the number of distinctive query terms (the denominator).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content words
(glue stripped), NO stemming, NO synonymy. A paraphrased result (same meaning,
different words) may score low — that is the precision/recall tradeoff: this
detector prefers flagging a paraphrase (false positive) over burying a real match
behind a phony semantic equivalence (false negative). A semantic reranker can
confirm downstream.

**Honesty rules (load-bearing):**

* A query with no distinctive terms (empty or all-glue) is ``unmeasurable`` —
  ``ndcg`` / ``top_relevance`` / ``mean_relevance`` are all ``None``, verdict
  ``unknown`` (defer — never fabricated).
* A result list with zero entries is ``unmeasurable`` — ``ndcg`` ``None`` (there is
  nothing to rank; verdict ``unknown``).
* ``IDCG == 0`` (every result has zero relevance — none of them address the query)
  -> ``ndcg`` is ``None`` and verdict ``irrelevant`` (defer — never ``0.0``; the
  distinction matters: ``None`` = couldn't normalize, ``irrelevant`` is the honest
  label).
* ``ndcg`` is in ``[0.0, 1.0]``; ``relevance_i`` in ``[0.0, 1.0]``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock,
  no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Pure-Python, no imports beyond the standard
library (the query and results are plain ``str`` inputs; the route layer supplies
them from the twin substrate / search index).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

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
        "other", "such", "own", "same", "too", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (grammatical glue stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


class SearchQualityError(ValueError):
    """A search-quality input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ResultRankRelevance:
    """One ranked result's relevance to the query."""

    position: int  # 0-indexed rank
    relevance: float  # |result_terms ∩ query_terms| / |query_terms|, in [0,1]
    matched_query_terms: tuple[str, ...]  # query terms present in this result


@dataclass(frozen=True)
class SearchQualityReport:
    """The ranking's quality. Advisory, pure."""

    ndcg: float | None  # DCG/IDCG in [0,1]; None when IDCG=0 or unmeasurable
    top_relevance: float | None  # relevance@0; None when no results
    mean_relevance: float  # average relevance; 0.0 when no results
    result_relevances: tuple[ResultRankRelevance, ...]
    query_term_count: int
    result_count: int
    verdict: str  # optimal | well_ranked | poor | irrelevant | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _relevance(query_terms: frozenset[str], result_terms: frozenset[str]) -> float:
    """Fraction of query terms the result covers. In [0,1]. Assumes query non-empty."""
    if not query_terms:
        return 0.0
    return len(query_terms & result_terms) / len(query_terms)


def _dcg(relevances: list[float]) -> float:
    """Discounted cumulative gain: Σ rel_i / log2(i + 2)."""
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def measure_search_quality(
    query: str,
    results: tuple[str, ...],
) -> SearchQualityReport:
    """Measure the ranking quality of ``results`` against ``query``.

    ``query`` is the search query text. ``results`` is the ranked result list
    (position 0 = top), each entry a result's text (an insight, a passage).
    Returns a :class:`SearchQualityReport` with the NDCG rank-discounted quality
    and per-position relevance.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not isinstance(results, tuple):
        raise SearchQualityError(
            f"results must be a tuple (ranked list), got {type(results).__name__}"
        )

    query_terms = _distinctive_terms(query)

    # Unmeasurable: query with no distinctive terms.
    if not query_terms:
        return SearchQualityReport(
            ndcg=None,
            top_relevance=None if not results else 0.0,
            mean_relevance=0.0,
            result_relevances=(),
            query_term_count=0,
            result_count=len(results),
            verdict="unknown",
            notes=(
                "search quality measures whether a RANKED result list puts "
                "query-relevant content first (NDCG over distinctive-term overlap) — "
                "the missing measurement surface for intelligent search (ask #14); "
                "the 20 artifact-quality axes score the artifacts, not the ranking",
                "NDCG: DCG = Σ relevance_i / log2(i+2); normalized by IDCG (the best "
                "possible ranking of the same results); 1.0 = optimal ranking, None "
                "when every result is irrelevant (IDCG=0) or the query is unmeasurable",
                "lexical floor (no stemming/synonymy): a paraphrased result (same "
                "meaning, different words) may score low — this detector prefers "
                "flagging a paraphrase (false positive) over burying a real match "
                "(false negative); a semantic reranker can confirm downstream",
                "query has no distinctive terms (empty or all-glue) — search quality "
                "is not measurable (defer — never fabricated)",
            ),
            authority="advisory",
        )

    per_rank: list[ResultRankRelevance] = []
    relevances: list[float] = []
    for position, result in enumerate(results):
        result_terms = _distinctive_terms(result)
        rel = _relevance(query_terms, result_terms)
        matched = tuple(sorted(query_terms & result_terms))
        per_rank.append(
            ResultRankRelevance(
                position=position,
                relevance=rel,
                matched_query_terms=matched,
            )
        )
        relevances.append(rel)

    result_count = len(relevances)
    mean_relevance = sum(relevances) / result_count if result_count else 0.0
    top_relevance = relevances[0] if relevances else None

    idcg = _dcg(sorted(relevances, reverse=True))
    dcg = _dcg(relevances)
    if result_count == 0:
        # No results to rank — distinct from "all results irrelevant".
        ndcg = None
        verdict = "unknown"
    elif idcg == 0.0:
        ndcg = None
        verdict = "irrelevant"
    else:
        ndcg = dcg / idcg
        if ndcg >= 0.90:
            verdict = "optimal"
        elif ndcg >= 0.60:
            verdict = "well_ranked"
        else:
            verdict = "poor"

    notes: list[str] = [
        "search quality measures whether a RANKED result list puts "
        "query-relevant content first (NDCG over distinctive-term overlap) — "
        "the missing measurement surface for intelligent search (ask #14); "
        "the 20 artifact-quality axes score the artifacts, not the ranking",
        "NDCG: DCG = Σ relevance_i / log2(i+2); normalized by IDCG (the best "
        "possible ranking of the same results); 1.0 = optimal ranking, None "
        "when every result is irrelevant (IDCG=0) or the query is unmeasurable",
        "lexical floor (no stemming/synonymy): a paraphrased result (same "
        "meaning, different words) may score low — this detector prefers "
        "flagging a paraphrase (false positive) over burying a real match "
        "(false negative); a semantic reranker can confirm downstream",
    ]
    if result_count == 0:
        notes.append(
            "no results to rank — ranking quality is not measurable (verdict "
            "unknown — defer, never fabricated)"
        )
    elif ndcg is None:
        notes.append(
            f"IDCG is 0: none of the {result_count} result(s) address any of the "
            f"{len(query_terms)} query term(s) — ranking quality is not measurable "
            "(verdict irrelevant — defer, never 0.0)"
        )
    else:
        notes.append(
            f"NDCG {ndcg:.0%}: top relevance {top_relevance:.0%}, mean "
            f"{mean_relevance:.0%} over {result_count} result(s) and "
            f"{len(query_terms)} query term(s) -> verdict {verdict}"
        )

    return SearchQualityReport(
        ndcg=ndcg,
        top_relevance=top_relevance,
        mean_relevance=mean_relevance,
        result_relevances=tuple(per_rank),
        query_term_count=len(query_terms),
        result_count=result_count,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "ResultRankRelevance",
    "SearchQualityError",
    "SearchQualityReport",
    "measure_search_quality",
]
