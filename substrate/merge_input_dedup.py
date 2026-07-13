"""Merge input-deduplication axis — how redundant were a merge's parent inputs?

When the operator (or a collective-merge) gathers ``N`` parent instances to merge into one
asset, this axis measures how many of those inputs were EXACT duplicates of each other BEFORE
any dedup happened. It answers: *"of the things I tried to merge, how many were copies?"*

A high ratio means the merge set was bloated with duplicate content (the operator selected the
same document twice, or N collective instances converged to identical output and were merged
blindly). A ratio of ``0`` means every input was distinct — the merge genuinely combined
different content. This is an INPUT-STAGE redundancy measurement, distinct from the merge-output
axes:

* ``merge_integrity`` (#1962) asks: did the merged OUTPUT retain the parents' content?
* ``redundancy`` (#1939) asks: within the MERGED OUTPUT, how much is duplicated?
* THIS axis asks: among the INPUTS, how many were duplicates of each other?

**Measured fields:**

* ``input_count`` — number of parent instances fed into the merge.
* ``unique_count`` — number of distinct inputs (by whitespace-normalized exact match).
* ``duplicate_count`` = ``input_count - unique_count`` — inputs that were copies of another.
* ``dedup_ratio`` = ``duplicate_count / input_count`` (``0.0`` = all inputs distinct, ``1.0`` =
  every input was a copy; ``None`` only for ``unknown``).
* ``duplicate_group_count`` — distinct content-groups that had ``>= 2`` members (the number of
  collision clusters; ``None`` for ``unknown``).
* ``largest_duplicate_group`` — the biggest collision cluster's size (the worst single overlap;
  ``None`` for ``unknown`` or when no group has ``>= 2`` members).
* ``duplicate_groups`` — every collision cluster as ``(hash_key, count)`` sorted desc by count,
  then by hash (auditable: the operator sees the full collision distribution, not a black-box
  ratio). Empty when there are no duplicates.

**Exact-match definition (load-bearing):** two inputs are duplicates iff their
whitespace-normalized text is byte-identical. Normalization is ``\\r``/``\\r\\n`` → ``\\n`` plus
outer ``.strip()`` — it preserves internal structure (paragraphs, spacing) so it honors
"exact." It does NOT lowercase, stem, or collapse internal whitespace, so semantically-similar
but textually-different inputs are NOT counted as duplicates (lexical floor, not semantic).
``hash_key`` is the first 12 hex chars of ``sha256`` over the normalized text — auditable and
non-reversible (the cluster is traceable without leaking raw content).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero inputs -> ``unknown`` (no merge to measure — defer, never fabricated).
* one input -> ``single_input`` (one parent — no other input to be a duplicate OF; honest base
  case distinct from ``unknown`` which has none and from ``all_distinct`` which has ``>= 2``).
* ``dedup_ratio == 0`` -> ``all_distinct`` (every input was unique — the merge combined
  genuinely different content).
* ``0 < dedup_ratio < majority_threshold`` (default ``0.50``) -> ``partial_redundant`` (some
  inputs were copies — mild overlap).
* ``dedup_ratio >= majority_threshold`` -> ``majority_redundant`` (most inputs were copies — the
  merge set was dominated by duplicate content).

**DESCRIPTIVE NOT NORMATIVE:** ``majority_redundant`` does NOT mean "bad" — the operator may
intentionally merge duplicate collective instances to weight that content more heavily, or the
duplicates may signal strong cross-instance convergence (a feature, not a bug). ``all_distinct``
does NOT mean "good" — distinct inputs could be contradictory noise. The operator judges whether
the input redundancy reflects merge INTENT. This axis surfaces the FACT of input overlap; it does
not prescribe the right redundancy.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero inputs are supplied.
* ``single_input`` is its own honest base case (one parent — distinct from ``unknown`` and from
  ``all_distinct`` which requires ``>= 2`` distinct inputs).
* ``dedup_ratio`` is ``None`` only for ``unknown``; for ``single_input`` it is an honest ``0.0``
  (one input, zero duplicates — literal truth, the verdict carries the state distinction).
* ``duplicate_group_count`` / ``largest_duplicate_group`` are ``None`` for ``unknown``; they are
  ``0`` / ``None`` respectively when duplicates exist nowhere (``all_distinct``).
* ``majority_threshold`` is scale-invariant: a 0.5 threshold means "at least half the inputs were
  copies" whether the merge had 4 or 400 inputs.
* every collision cluster auditable via ``duplicate_groups`` (hash + count — no black-box ratio).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; hash keys + sorted output are reproducible).
* import-free of off-main siblings (plain ``str`` document inputs; route layer adapts 1:1 from
  the merge parent-body list).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "DuplicateGroup",
    "MergeInputDedupReport",
    "measure_merge_input_dedup",
]

_DEFAULT_MAJORITY_THRESHOLD = 0.50


@dataclass(frozen=True)
class DuplicateGroup:
    """One collision cluster: inputs sharing identical normalized content."""

    hash_key: str  # sha256[:12] of normalized text — auditable, non-reversible
    count: int  # number of inputs in this cluster (>= 2)


@dataclass(frozen=True)
class MergeInputDedupReport:
    """The merge input-deduplication surface for one merge. Advisory, pure."""

    input_count: int
    unique_count: int | None
    duplicate_count: int | None
    dedup_ratio: float | None
    duplicate_group_count: int | None
    largest_duplicate_group: int | None
    duplicate_groups: tuple[DuplicateGroup, ...]
    majority_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _normalize(text: str) -> str:
    r"""Normalize text for exact-match dedup.

    Line-ending normalization (``\r\n`` / ``\r`` -> ``\n``) plus outer ``.strip()``. Preserves
    internal structure (paragraphs, spacing). Does NOT lowercase, stem, or collapse internal
    whitespace — lexical floor, not semantic.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _hash_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def measure_merge_input_dedup(
    input_texts: Sequence[str],
    *,
    majority_threshold: float = _DEFAULT_MAJORITY_THRESHOLD,
) -> MergeInputDedupReport:
    r"""Measure how redundant a merge's parent inputs were.

    ``input_texts`` are the document bodies (or raw text) of each parent instance fed into a
    merge (the route layer supplies these from the merge parent-body list). Returns a
    :class:`MergeInputDedupReport` quantifying input-stage exact-duplicate overlap.

    Raises:
        ValueError: if ``majority_threshold`` is outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= majority_threshold <= 1.0:
        raise ValueError(
            f"majority_threshold must be in [0.0, 1.0]; got {majority_threshold}"
        )

    input_count = len(input_texts)

    if input_count == 0:
        return MergeInputDedupReport(
            input_count=0,
            unique_count=None,
            duplicate_count=None,
            dedup_ratio=None,
            duplicate_group_count=None,
            largest_duplicate_group=None,
            duplicate_groups=(),
            majority_threshold=majority_threshold,
            verdict="unknown",
            notes=("no inputs — merge input redundancy unmeasurable",),
        )

    # Group inputs by normalized-content hash key.
    buckets: dict[str, int] = {}
    for text in input_texts:
        key = _hash_key(_normalize(text))
        buckets[key] = buckets.get(key, 0) + 1

    unique_count = len(buckets)
    duplicate_count = input_count - unique_count
    dedup_ratio = duplicate_count / input_count

    duplicate_groups = sorted(
        (DuplicateGroup(hash_key=k, count=c) for k, c in buckets.items() if c >= 2),
        key=lambda g: (g.count, g.hash_key),
        reverse=True,
    )
    duplicate_group_count = len(duplicate_groups)
    largest_duplicate_group = (
        max((g.count for g in duplicate_groups), default=0) if duplicate_groups else None
    )

    if input_count == 1:
        return MergeInputDedupReport(
            input_count=1,
            unique_count=unique_count,
            duplicate_count=duplicate_count,
            dedup_ratio=dedup_ratio,
            duplicate_group_count=0,
            largest_duplicate_group=None,
            duplicate_groups=(),
            majority_threshold=majority_threshold,
            verdict="single_input",
            notes=(
                "one parent — no other input to be a duplicate of (honest base case distinct "
                "from unknown and all_distinct)",
            ),
        )

    if dedup_ratio == 0.0:
        verdict = "all_distinct"
        notes = ("every input was distinct — the merge combined genuinely different content",)
    elif dedup_ratio >= majority_threshold:
        verdict = "majority_redundant"
        notes = (
            f"dedup_ratio {dedup_ratio:.4f} >= majority_threshold {majority_threshold:.2f} — "
            "most inputs were copies of another",
        )
    else:
        verdict = "partial_redundant"
        notes = (
            f"dedup_ratio {dedup_ratio:.4f} < majority_threshold {majority_threshold:.2f} — "
            "some inputs were copies",
        )

    return MergeInputDedupReport(
        input_count=input_count,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        dedup_ratio=dedup_ratio,
        duplicate_group_count=duplicate_group_count,
        largest_duplicate_group=largest_duplicate_group,
        duplicate_groups=tuple(duplicate_groups),
        majority_threshold=majority_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
