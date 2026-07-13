r"""Merge contribution-orthogonality axis — do merged parents contribute disjoint or overlapping content?

Operator vision (ask #3): *"...merge various sub-agent deep researches after they come to completion
to create a written analysis, or maybe I want to click on multiple of these sub agents to engage in a
collective deep research where I merge those instances and prompt them as a cohesive unit."* When N
instances merge "as a cohesive unit," the IDEAL is that each parent contributes ORTHOGONAL (non-
overlapping) value — together they cover more ground than any one alone. The FAILURE mode is a
collective that merely RESTATES itself: every parent paraphrases the same content in different words.
Such a merge is "collective" in name only; the parents add no breadth. No existing merge axis measures
the LEXICAL overlap BETWEEN parents.

**Genuinely distinct from the merge + redundancy surface (load-bearing):**

* ``merge_input_dedup`` (#2008): EXACT-MATCH duplicate inputs (byte-identical after whitespace
  normalization). Two parents with ZERO exact-match overlap (dedup says ``all_distinct``) can still
  share heavy LEXICAL content (paraphrases of the same findings). Dedup catches copies; orthogonality
  catches paraphrased redundancy. Different machinery (content-term Jaccard vs sha256 exact hash).
* ``merge_source_balance`` (#2015): per-parent OUTPUT share / dominance (is one parent drowning out
  the others). A merge can be perfectly balanced (each parent 25 %) yet maximally non-orthogonal (all
  four say the same thing). Balance asks "who dominates"; orthogonality asks "who repeats."
* ``collective_coherence`` (#1976): do the merged parts CONNECT (semantic cohesion). Coherence and
  orthogonality are COMPLEMENTARY, not redundant: the ideal collective is both COHERENT (parts relate)
  AND ORTHOGONAL (parts don't restate). Coherence measures connection; orthogonality measures
  redundancy — opposite concerns that can disagree (a merge can be highly coherent precisely BECAUSE
  the parents overlap heavily).
* ``insight_redundancy`` (#1939): within the MERGED OUTPUT, does the artifact repeat itself. This is
  BETWEEN the PARENTS (input-stage pairwise overlap) — a different object and a different stage.

**The binding distinctness:** contribution-orthogonality is the only axis measuring PAIRWISE LEXICAL
overlap between merge parents — the redundancy-of-contribution that exact-dedup misses (paraphrases)
and that output-redundancy cannot see (it runs after the merge). It tells the operator whether a
"cohesive unit" merge is genuinely additive (orthogonal parents) or merely restated (overlapping parents).

**The measurement (hard to vary).** For each parent, extract its distinctive terms (lowercase content
words, grammatical glue stripped — the lexical floor). For each UNORDERED parent pair, compute the
Jaccard overlap:

    overlap(i, j) = |terms_i ∩ terms_j| / |terms_i ∪ terms_j|    in ``[0, 1]``

``0`` = the two parents share no content vocabulary (fully orthogonal); ``1`` = identical content
vocabulary (fully redundant). The report carries:

* ``mean_overlap`` — the mean Jaccard over all MEASURABLE pairs (both parents have distinctive terms).
* ``pair_count`` / ``measurable_pair_count`` — total unordered pairs and how many were measurable.
* ``orthogonality`` = ``1 - mean_overlap`` in ``[0, 1]`` (``1`` = fully additive, ``0`` = fully
  restated — the readability-friendly inverse for the UI).
* ``max_pair_overlap`` — the worst single pair (the most redundant coupling; ``None`` when no pair is
  measurable).
* ``pair_overlaps`` — every measurable pair's ``(parent_a, parent_b, overlap)`` sorted desc by overlap
  (auditable: the operator sees the full coupling structure, not a black-box mean).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content words (glue stripped).
NO stemming, NO synonymy. This means two parents that say the same thing in different words (a
paraphrase) score LOWER overlap than their true semantic redundancy — this detector UNDER-counts
paraphrased overlap (conservative). That is the honest posture for a "redundancy" axis: it never
FABRICATES overlap that isn't lexically present, so ``highly_orthogonal`` is a floor guarantee (the
parents genuinely share little vocabulary), while ``highly_overlapping`` is strong evidence of true
restatement. The operator can confirm semantic overlap downstream.

**Why orthogonality diverges from dedup (the worked example):** two parents — A: *"transformers use
self-attention"* and B: *"self-attention powers transformer models."* Exact-match dedup says
``all_distinct`` (different byte strings). But their distinctive-term sets overlap heavily ({transformer,
self, attention, model}), so Jaccard is high → orthogonality is low. Dedup says "distinct inputs";
orthogonality says "redundant contributions." Only the lexical overlap sees the paraphrase.

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero parents -> ``unknown`` (no merge to measure — defer, never fabricated).
* one parent -> ``single_input`` (no pair to compare — honest base case distinct from ``unknown``).
* ``>= 2`` parents but zero measurable pairs (all parents lack distinctive terms) -> ``unmeasurable``
  (defer — no content vocabulary to overlap; never fabricated ``highly_orthogonal``).
* ``mean_overlap >= redundant_threshold`` (default ``0.60``) -> ``highly_overlapping`` (parents
  restate each other — a collective in name only, low additive value).
* ``mean_overlap <= orthogonal_threshold`` (default ``0.20``) -> ``highly_orthogonal`` (parents
  contribute disjoint content — a genuinely additive cohesive unit).
* otherwise -> ``partially_overlapping`` (a middle blend of unique and shared content).

**DESCRIPTIVE NOT NORMATIVE:** ``highly_orthogonal`` does NOT mean "good" — disjoint parents may be
off-topic noise with no shared thread (high orthogonality but poor coherence). ``highly_overlapping``
does NOT mean "bad" — deliberate cross-instance convergence (independent agents reaching the same
finding) is a feature, not a flaw. The operator judges whether the overlap reflects redundancy or
corroboration. This axis surfaces the FACT of contribution overlap; it does not prescribe the right
value.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero parents are supplied.
* ``single_input`` is its own honest base case (one parent — no pair; distinct from ``unknown`` and
  from any overlap verdict).
* ``unmeasurable`` is its own honest state (no distinctive terms to overlap) — ``mean_overlap`` /
  ``orthogonality`` are ``None``, NEVER a fabricated ``0.0`` (zero overlap is a real MEASURED state,
  ``unmeasurable`` is the absence of measurable pairs — they never collapse).
* ``mean_overlap`` / ``orthogonality`` are ``None`` only for ``unknown`` / ``single_input`` /
  ``unmeasurable``; for any measurable pair they are measured values.
* a pair where ONE parent lacks distinctive terms is UNMEASURABLE (excluded from the mean, never
  counted as ``0`` overlap which would falsely deflate the mean toward orthogonality).
* every pair's overlap surfaced in ``pair_overlaps`` (auditable, no black-box mean).
* thresholds are absolute fractions (scale-free: 0.60 overlap means 0.60 at 3 or 30 parents).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclass; sorted term sets + sorted output are reproducible).
* import-free of off-main siblings (plain ``str`` parent texts; route layer adapts 1:1 from the merge
  parent-body list).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "MergeContributionOrthogonalityReport",
    "measure_merge_contribution_orthogonality",
]

_DEFAULT_REDUNDANT_THRESHOLD = 0.60
_DEFAULT_ORTHOGONAL_THRESHOLD = 0.20

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
        "it", "its", "they", "them", "their", "there", "here",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "such", "now", "i", "we", "you", "he", "she",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (grammatical glue stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


@dataclass(frozen=True)
class PairOverlap:
    """One parent-pair's auditable lexical overlap."""

    parent_a: str
    parent_b: str
    overlap: float


@dataclass(frozen=True)
class MergeContributionOrthogonalityReport:
    """The contribution-orthogonality surface for one merge. Advisory, pure."""

    parent_count: int
    pair_count: int
    measurable_pair_count: int
    mean_overlap: float | None
    orthogonality: float | None
    max_pair_overlap: float | None
    pair_overlaps: tuple[PairOverlap, ...]
    redundant_threshold: float
    orthogonal_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_merge_contribution_orthogonality(
    parent_texts: Sequence[str],
    *,
    redundant_threshold: float = _DEFAULT_REDUNDANT_THRESHOLD,
    orthogonal_threshold: float = _DEFAULT_ORTHOGONAL_THRESHOLD,
) -> MergeContributionOrthogonalityReport:
    r"""Measure how much merged parents' contributions overlap (vs contribute orthogonally).

    Args:
        parent_texts: the body text of each parent instance fed into a merge.
        redundant_threshold: mean overlap at/above which parents are ``highly_overlapping``
            (default ``0.60``).
        orthogonal_threshold: mean overlap at/below which parents are ``highly_orthogonal``
            (default ``0.20``).

    Returns:
        A :class:`MergeContributionOrthogonalityReport` with the mean pairwise overlap and verdict.

    Raises:
        ValueError: if thresholds are outside their valid ranges or out of order.
    """
    if not 0.0 <= orthogonal_threshold <= 1.0:
        raise ValueError(
            f"orthogonal_threshold must be in [0.0, 1.0]; got {orthogonal_threshold}"
        )
    if not 0.0 <= redundant_threshold <= 1.0:
        raise ValueError(
            f"redundant_threshold must be in [0.0, 1.0]; got {redundant_threshold}"
        )
    if not orthogonal_threshold <= redundant_threshold <= 1.0:
        raise ValueError(
            f"redundant_threshold ({redundant_threshold}) must be in "
            f"[orthogonal_threshold ({orthogonal_threshold}), 1.0]"
        )

    parent_count = len(parent_texts)

    if parent_count == 0:
        return MergeContributionOrthogonalityReport(
            parent_count=0,
            pair_count=0,
            measurable_pair_count=0,
            mean_overlap=None,
            orthogonality=None,
            max_pair_overlap=None,
            pair_overlaps=(),
            redundant_threshold=redundant_threshold,
            orthogonal_threshold=orthogonal_threshold,
            verdict="unknown",
            notes=("no parents — contribution overlap unmeasurable",),
        )

    term_sets: list[frozenset[str]] = [
        _distinctive_terms(text) for text in parent_texts
    ]

    if parent_count == 1:
        return MergeContributionOrthogonalityReport(
            parent_count=1,
            pair_count=0,
            measurable_pair_count=0,
            mean_overlap=None,
            orthogonality=None,
            max_pair_overlap=None,
            pair_overlaps=(),
            redundant_threshold=redundant_threshold,
            orthogonal_threshold=orthogonal_threshold,
            verdict="single_input",
            notes=("one parent — no pair to compare",),
        )

    pair_count = parent_count * (parent_count - 1) // 2
    pair_overlaps: list[PairOverlap] = []
    overlap_sum = 0.0
    for i in range(parent_count):
        for j in range(i + 1, parent_count):
            ti, tj = term_sets[i], term_sets[j]
            # A pair is measurable only if BOTH parents have distinctive terms.
            if not ti or not tj:
                continue
            union = ti | tj
            overlap = len(ti & tj) / len(union)
            overlap_sum += overlap
            pair_overlaps.append(
                PairOverlap(parent_a=f"parent_{i}", parent_b=f"parent_{j}", overlap=overlap)
            )

    pair_overlaps.sort(key=lambda p: (p.overlap, p.parent_a, p.parent_b), reverse=True)
    measurable_pair_count = len(pair_overlaps)

    if measurable_pair_count == 0:
        return MergeContributionOrthogonalityReport(
            parent_count=parent_count,
            pair_count=pair_count,
            measurable_pair_count=0,
            mean_overlap=None,
            orthogonality=None,
            max_pair_overlap=None,
            pair_overlaps=(),
            redundant_threshold=redundant_threshold,
            orthogonal_threshold=orthogonal_threshold,
            verdict="unmeasurable",
            notes=(
                f"{parent_count} parents but zero measurable pairs — no content "
                "vocabulary to overlap",
            ),
        )

    mean_overlap = overlap_sum / measurable_pair_count
    orthogonality = 1.0 - mean_overlap
    max_pair_overlap = pair_overlaps[0].overlap

    if mean_overlap >= redundant_threshold:
        verdict = "highly_overlapping"
        notes = (
            f"mean_overlap {mean_overlap:.4f} >= redundant_threshold "
            f"{redundant_threshold:.2f} — parents restate each other "
            "(a collective in name only, low additive value)",
        )
    elif mean_overlap <= orthogonal_threshold:
        verdict = "highly_orthogonal"
        notes = (
            f"mean_overlap {mean_overlap:.4f} <= orthogonal_threshold "
            f"{orthogonal_threshold:.2f} — parents contribute disjoint content "
            "(a genuinely additive cohesive unit)",
        )
    else:
        verdict = "partially_overlapping"
        notes = (
            f"mean_overlap {mean_overlap:.4f} between thresholds — "
            "a middle blend of unique and shared content",
        )

    return MergeContributionOrthogonalityReport(
        parent_count=parent_count,
        pair_count=pair_count,
        measurable_pair_count=measurable_pair_count,
        mean_overlap=mean_overlap,
        orthogonality=orthogonality,
        max_pair_overlap=max_pair_overlap,
        pair_overlaps=tuple(pair_overlaps),
        redundant_threshold=redundant_threshold,
        orthogonal_threshold=orthogonal_threshold,
        verdict=verdict,
        notes=notes,
    )
