r"""Search precision and recall — did the search return the right SET of results?

Operator vision (ask #14): *"...intelligent search over my dream of an infinite
information platform."* ``search_quality`` (#1957) measures RANKING ORDER — given a
query and a ranked list, does the ranking put relevant things first (NDCG)? It
estimates relevance LEXICALLY (term overlap with the query) and normalizes against
the ideal ordering of the RETURNED set. It does NOT measure result-SET quality:
how much NOISE is in the returned set (precision), and how much was MISSED
(recall). And it cannot — NDCG normalizes by the returned set's own ideal ranking,
so a set of [one relevant item, nine noise items] scores high NDCG (the relevant
item is ranked first) while precision is 0.10 (90 percent noise). NDCG also says
nothing about recall: it cannot know about relevant items the search FAILED to
return.

**Genuinely distinct (different question, different input):**

* ``search_quality`` (#1957): RANKING ORDER (NDCG). Input: query text + ranked
  result texts. Relevance: LEXICAL estimation (term overlap). Question: does the
  ranking put relevant things FIRST?
* THIS (``search_precision_recall``): result-SET QUALITY (precision + recall).
  Input: the returned result set + GROUND-TRUTH relevance labels + the total
  relevant count. Relevance: GROUND-TRUTH (human/benchmark-labeled — not estimated).
  Question: did the search return the RIGHT SET — not too much noise, not missing
  things?

They are orthogonal and complementary. NDCG optimizes the ORDER of what was
returned; precision/recall measures the SET itself. A search can have perfect NDCG
(precision@1 = 1.0, the top hit is relevant) yet abysmal precision overall (0.10)
and abysmal recall (found 1 of 20 relevant items). The precision/recall pair is the
atomic IR unit for set quality — search_quality needs it as a complement because
ranking quality and set quality are independent failure modes.

**Why ground-truth labels (load-bearing).** Precision and recall are DEFINED over
labeled relevance — they are meaningless without a ground-truth judgment of which
results are truly relevant. search_quality avoids this by estimating relevance
lexically (a reasonable proxy when labels are unavailable). But when the recursive
benchmark (ask #11) provides ground-truth relevance judgments for its test queries,
precision/recall is the HARDER, more honest metric: it measures against truth, not
a lexical proxy. The route layer supplies the ground-truth labels from the
benchmark's labeled query-result pairs.

**The measurement (hard to vary).** Given the returned result ids, a set of ids
labeled relevant (ground truth), and the total count of relevant items that exist
in the corpus:

* ``true_positives`` = |returned ∩ relevant| — correctly returned relevant items.
* ``false_positives`` = |returned \ relevant| — returned but NOT relevant (noise).
* ``false_negatives`` = |relevant \ returned| — relevant but NOT returned (missed).
* ``precision = true_positives / |returned|`` — in ``[0, 1]`` (what fraction of
  returned results were actually relevant — the noise rate). Boundary: when
  ``|returned| == 0``, precision is ``None`` (defer — a search that returns nothing
  has no noise, but also no signal; fabricating 1.0 would hide a broken search
  behind a phony perfect score).
* ``recall = true_positives / total_relevant`` — in ``[0, 1]`` (what fraction of
  relevant items were found — the coverage rate). Boundary: when
  ``total_relevant == 0``, recall is ``None`` (defer — a query with no relevant
  items in the corpus has nothing to recall; fabricating 1.0 would be dishonest).
* ``f1 = 2 * precision * recall / (precision + recall)`` — the harmonic mean (the
  balanced single score). ``None`` when either precision or recall is ``None``.

**Verdict (distinct honest states, never collapsed):**

* ``|returned| == 0`` AND ``total_relevant == 0`` -> ``unknown`` (defer — nothing
  returned and nothing to find; never fabricated).
* precision and/or recall computable -> the verdict is driven by the WORST of the
  two (a search that returns everything with 90 percent noise is not "good" just
  because recall is high):
  * ``precision >= high_threshold`` AND ``recall >= high_threshold`` (default
    ``0.80``) -> ``high_quality`` (both set-quality dimensions strong).
  * ``precision < low_threshold`` (default ``0.30``) -> ``noisy`` (too much noise
    in the result set — the operator wades through irrelevance).
  * ``recall < low_threshold`` -> ``incomplete`` (too much missed — the search
    fails to surface relevant content).
  * otherwise -> ``adequate`` (the common middle ground — neither dimension
    critically weak nor both strong).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when both sides are empty (nothing returned AND
  nothing relevant).
* ``precision`` ``None`` when ``|returned| == 0`` (defer — never ``1.0`` or
  ``0.0``; an empty result set is not "perfect precision" nor "zero precision").
* ``recall`` ``None`` when ``total_relevant == 0`` (defer — never ``1.0``).
* ``f1`` ``None`` when either component is ``None``.
* ``total_relevant`` must be >= 0 (raises); ``returned`` ids and ``relevant`` ids
  are treated as sets (duplicates de-duplicated).
* Ground-truth labels are the authority — this module never ESTIMATES relevance
  (that is search_quality's lane); it measures against provided labels.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Takes plain id sets + counts; the route
layer adapts 1:1 from the search engine's result set and the benchmark's labeled
relevance judgments. Pure-Python: stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_HIGH_THRESHOLD: float = 0.80
_DEFAULT_LOW_THRESHOLD: float = 0.30


class SearchPrecisionRecallError(ValueError):
    """A search-precision-recall input violates a load-bearing invariant."""


@dataclass(frozen=True)
class SearchPrecisionRecallReport:
    """The result-set quality verdict. Advisory, pure."""

    returned_count: int
    relevant_returned_count: int  # true positives
    total_relevant: int
    true_positives: int
    false_positives: int  # returned but not relevant (noise)
    false_negatives: int  # relevant but not returned (missed)
    precision: float | None  # tp / returned; None when |returned| == 0
    recall: float | None  # tp / total_relevant; None when total_relevant == 0
    f1: float | None  # harmonic mean; None when either component None
    high_threshold: float
    low_threshold: float
    verdict: str  # high_quality | noisy | incomplete | adequate | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_search_precision_recall(
    returned_ids: Sequence[str],
    relevant_ids: Sequence[str],
    total_relevant: int,
    *,
    high_threshold: float = _DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = _DEFAULT_LOW_THRESHOLD,
) -> SearchPrecisionRecallReport:
    """Measure the precision and recall of a search result set.

    ``returned_ids`` is the set of ids the search returned.
    ``relevant_ids`` is the ground-truth set of relevant ids (the labels).
    ``total_relevant`` is the total count of relevant items in the corpus (>= the
    relevant ids that were returned; may exceed it if some relevant items were
    never returned and thus not in the label set). Returns a
    :class:`SearchPrecisionRecallReport`.

    Raises:
        SearchPrecisionRecallError: if ``total_relevant`` is negative, thresholds
            are invalid, or ``high_threshold <= low_threshold``.
    """
    if total_relevant < 0:
        raise SearchPrecisionRecallError(
            f"total_relevant must be non-negative; got {total_relevant}"
        )
    if not 0.0 < high_threshold <= 1.0:
        raise SearchPrecisionRecallError(
            f"high_threshold must be in (0.0, 1.0]; got {high_threshold}"
        )
    if not 0.0 <= low_threshold < 1.0:
        raise SearchPrecisionRecallError(
            f"low_threshold must be in [0.0, 1.0); got {low_threshold}"
        )
    if high_threshold <= low_threshold:
        raise SearchPrecisionRecallError(
            f"high_threshold ({high_threshold}) must exceed low_threshold "
            f"({low_threshold})"
        )

    returned_set = set(returned_ids)
    relevant_set = set(relevant_ids)

    returned_count = len(returned_set)
    true_positives = len(returned_set & relevant_set)
    false_positives = len(returned_set - relevant_set)
    # false_negatives: relevant items not returned (within the labeled set).
    false_negatives = len(relevant_set - returned_set)

    precision: float | None = None
    if returned_count > 0:
        precision = true_positives / returned_count

    recall: float | None = None
    if total_relevant > 0:
        recall = true_positives / total_relevant

    f1: float | None = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)

    if returned_count == 0 and total_relevant == 0:
        verdict = "unknown"
        notes = ("nothing returned and nothing relevant to find",)
    elif precision is not None and recall is not None:
        if precision >= high_threshold and recall >= high_threshold:
            verdict = "high_quality"
        elif precision < low_threshold:
            verdict = "noisy"
        elif recall < low_threshold:
            verdict = "incomplete"
        else:
            verdict = "adequate"
        notes = (
            f"precision {precision:.4f}, recall {recall:.4f}"
            + (f", f1 {f1:.4f}" if f1 is not None else ""),
        )
    elif precision is not None:
        # recall is None (total_relevant == 0): all returned items are noise.
        verdict = "noisy" if returned_count > 0 else "unknown"
        notes = (
            f"precision {precision:.4f}; recall undefined (total_relevant 0)",
        )
    else:
        # precision is None (returned_count == 0) but total_relevant > 0.
        verdict = "incomplete"
        notes = (
            f"recall {recall:.4f}; precision undefined (nothing returned)",
        )

    return SearchPrecisionRecallReport(
        returned_count=returned_count,
        relevant_returned_count=true_positives,
        total_relevant=total_relevant,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        verdict=verdict,
        notes=notes,
    )
