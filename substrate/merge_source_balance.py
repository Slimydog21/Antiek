"""Merge source-balance axis — is one merge parent drowning out the others?

When the operator (or a collective-merge) merges ``N`` parent instances into one asset, this axis
measures how the OUTPUT is distributed across those parents. It answers: *"of the merged output,
did every parent get a fair hearing, or did one voice dominate?"*

This is the ``collective deep research`` accountability surface (ask #3): the operator's explicit
vision is to merge several sub-agent deep-research instances "as a cohesive unit." But a merge is
only genuinely *collective* when no parent is silenced. A merge labeled "5-way" where one parent
supplies 95 % of the output and four contribute nothing is a merge in name only — the collective
was theater. This axis surfaces the FACT of per-parent output share so the operator can judge
whether the balance reflects merge intent.

**Distinct from the other merge axes (the binding constraint — each asks a different question):**

* ``merge_integrity`` (#1962) — did the OUTPUT *retain* every parent's content (nothing lost)?
  That is completeness; THIS is distribution. A merge can retain everything yet be 99 %/1 %.
* ``merge_input_dedup`` (#2008) — were the INPUTS duplicates of each other (pre-merge redundancy)?
  That is input-stage overlap; THIS is output-stage attribution.
* ``collective_coherence`` (#1976) — do the N merged instances *cohere* into one unit? That is
  semantic cohesion; THIS is statistical balance (a perfectly balanced merge can still be
  incoherent, and a coherent merge can be single-sourced).
* ``provenance_traceability`` (#1993) — can every insight be *traced* to a source? That is
  traceability + the preserved/synthesized/generative MODE split; THIS is the per-parent share
  WITHIN the preserved set (a different cut of the same provenance, not a re-label: the split
  counts three MODES, this measures N PARENTS' evenness).
* ``draft_divergence`` (#1974) — how far did the draft *drift* from parents pre-merge? That is
  content divergence; THIS is attributional concentration.

**Two independent concentration lenses (both carried, neither collapsed):**

* ``max_share`` — the single largest parent's fraction of the attributed output (peak dominance).
  Bounded below by ``1 / n`` (for ``n`` parents the top parent always holds ``>= 1/n``), so it is
  a poor *evenness* lens for small ``n`` (a perfectly fair 2-parent merge still has ``max_share``
  0.50) — hence the second lens.
* ``balance_entropy`` — normalized Shannon entropy of the per-parent share distribution, in
  ``[0, 1]`` (``1`` = perfectly even, ``0`` = one parent holds everything). Scale-free across
  parent counts: a fair 2-way (0.50/0.50) and a fair 5-way (0.20 each) both score ``1.0``.

The two lenses genuinely disagree and that disagreement is informative: a 2-parent 0.60/0.40
merge has high entropy (``0.97``) yet is dominated (``max_share 0.60``) — the entropy says "even
between two," the share says "one has the majority." The operator sees both.

**Measured fields:**

* ``attributed_count`` — output units attributed to exactly one parent (preserved content).
* ``unattributed_count`` — output units with no single parent (synthesized/generative). Carried
  verbatim so the balance denominator is never gamed; the mode split is #1993's job, not here.
* ``contributing_parent_count`` — distinct parents that supplied at least one attributed unit.
* ``silenced_parent_count`` — parents in the merge that supplied NOTHING (``None`` when the total
  parent count is unknown — never fabricated; ``0`` when every parent contributed).
* ``max_share`` / ``dominant_parent`` — the peak parent and its share.
* ``balance_entropy`` — normalized Shannon evenness.
* ``per_parent`` — every contributing parent as ``(parent_id, count, share)`` sorted by count desc
  then id asc (auditable: the operator sees the full share table, not a black-box score).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero attributed units -> ``unknown`` (nothing preserved to balance — defer, never fabricated).
* one contributing parent -> ``single_source`` (one parent voice — honest base case distinct from
  ``unknown`` which has nothing and from ``balanced`` which needs ``>= 2``).
* ``max_share >= dominance_threshold`` (default ``0.60``) -> ``dominated`` (one parent holds the
  majority — boundary inclusive).
* ``balance_entropy >= balance_entropy_threshold`` (default ``0.90``) and not dominated ->
  ``balanced`` (genuinely even across parents).
* otherwise -> ``skewed`` (between: no single majority, but uneven).

**DESCRIPTIVE NOT NORMATIVE:** ``dominated`` does NOT mean "bad" — one parent may genuinely have
had more to say, and a deliberate weight-merge intentionally over-represents a source.
``balanced`` does NOT mean "good" — an even split of contradictory noise is still noise.
``single_source`` does NOT mean "bad" — a 1-parent "merge" may be a correct single-source update.
The operator judges whether the balance reflects merge INTENT. This axis surfaces the FACT of
per-parent share; it does not prescribe the right distribution.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero units are attributed.
* ``single_source`` is its own honest base case (one parent — distinct from ``unknown``).
* ``silenced_parent_count`` is ``None`` when the total parent count is unknown, ``0`` when all
  contributed, and a real count otherwise — three distinct states never collapsed.
* ``max_share`` / ``balance_entropy`` are ``None`` only for ``unknown``; for one parent
  ``max_share`` is an honest ``1.0`` and ``balance_entropy`` an honest ``0.0`` (literal truth;
  the verdict carries the state distinction, not the score).
* every parent auditable via ``per_parent`` (id + count + share — no black-box score).
* thresholds are scale-invariant (a 0.60 dominance means "one parent holds >= 60 %" whether the
  merge had 3 or 300 attributed units).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted output is reproducible).
* import-free of off-main siblings (plain ``str`` parent-id inputs; route layer adapts 1:1 from
  the merged-output provenance map — one id per attributed output unit).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "MergeSourceBalanceReport",
    "ParentContribution",
    "measure_merge_source_balance",
]

_DEFAULT_DOMINANCE_THRESHOLD = 0.60
_DEFAULT_BALANCE_ENTROPY_THRESHOLD = 0.90


@dataclass(frozen=True)
class ParentContribution:
    """One parent's share of the attributed merged output."""

    parent_id: str
    count: int  # output units attributed to this parent (>= 1)
    share: float  # count / total_attributed, in (0.0, 1.0]


@dataclass(frozen=True)
class MergeSourceBalanceReport:
    """The per-parent output-balance surface for one merge. Advisory, pure."""

    attributed_count: int
    unattributed_count: int
    contributing_parent_count: int | None
    silenced_parent_count: int | None
    max_share: float | None
    dominant_parent: str | None
    balance_entropy: float | None
    per_parent: tuple[ParentContribution, ...]
    dominance_threshold: float
    balance_entropy_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _normalized_entropy(shares: Sequence[float]) -> float:
    """Normalized Shannon entropy of a share distribution in ``[0, 1]``.

    ``1.0`` = perfectly even across all parents; ``0.0`` = one parent holds everything. The raw
    entropy ``H = -sum(p log2 p)`` is divided by ``log2(n)`` (``n`` = parent count) so the score
    is scale-free: a fair 2-way and a fair 5-way both score ``1.0``. For one parent the divisor is
    ``log2(1) = 0``; the caller guards that case (returns ``0.0``, the honest single-voice floor).
    """
    n = len(shares)
    if n <= 1:
        return 0.0
    raw = -sum(p * math.log2(p) for p in shares if p > 0.0)
    return raw / math.log2(n)


def measure_merge_source_balance(
    parent_ids: Sequence[str],
    *,
    total_parents: int | None = None,
    dominance_threshold: float = _DEFAULT_DOMINANCE_THRESHOLD,
    balance_entropy_threshold: float = _DEFAULT_BALANCE_ENTROPY_THRESHOLD,
) -> MergeSourceBalanceReport:
    """Measure how evenly a merge's output is distributed across its parents.

    ``parent_ids`` are the source-parent identifiers of each OUTPUT unit attributed to exactly one
    parent (the route layer supplies these from the merged-output provenance map — one id per
    preserved insight/sentence). An empty/whitespace id marks an unattributed (synthesized or
    generative) unit: it is counted in ``unattributed_count`` and excluded from the balance
    denominator so the score is never gamed, but its mode analysis is deferred to
    ``provenance_traceability`` (#1993).

    ``total_parents`` (optional) is the total number of parents in the merge. When supplied it
    enables ``silenced_parent_count`` (parents that contributed nothing); it must be ``>=`` the
    number of distinct contributing parents or the inputs are inconsistent.

    Returns:
        A :class:`MergeSourceBalanceReport` quantifying per-parent output share.

    Raises:
        ValueError: if ``dominance_threshold`` or ``balance_entropy_threshold`` is outside
            ``[0.0, 1.0]``, or ``total_parents`` is negative or smaller than the distinct
            contributing-parent count.
    """
    if not 0.0 <= dominance_threshold <= 1.0:
        raise ValueError(
            f"dominance_threshold must be in [0.0, 1.0]; got {dominance_threshold}"
        )
    if not 0.0 <= balance_entropy_threshold <= 1.0:
        raise ValueError(
            f"balance_entropy_threshold must be in [0.0, 1.0]; got {balance_entropy_threshold}"
        )
    if total_parents is not None and total_parents < 0:
        raise ValueError(f"total_parents must be >= 0; got {total_parents}")

    attributed = [pid.strip() for pid in parent_ids if pid.strip()]
    attributed_count = len(attributed)
    unattributed_count = len(parent_ids) - attributed_count

    if attributed_count == 0:
        notes: tuple[str, ...] = ()
        if unattributed_count > 0:
            notes = (
                f"all {unattributed_count} output units were unattributed "
                f"(synthesized/generative) — nothing preserved to balance",
            )
        return MergeSourceBalanceReport(
            attributed_count=0,
            unattributed_count=unattributed_count,
            contributing_parent_count=None,
            silenced_parent_count=None,
            max_share=None,
            dominant_parent=None,
            balance_entropy=None,
            per_parent=(),
            dominance_threshold=dominance_threshold,
            balance_entropy_threshold=balance_entropy_threshold,
            verdict="unknown",
            notes=notes,
        )

    counts: dict[str, int] = {}
    for pid in attributed:
        counts[pid] = counts.get(pid, 0) + 1

    distinct = len(counts)

    if total_parents is not None and total_parents < distinct:
        raise ValueError(
            f"total_parents ({total_parents}) is smaller than the distinct contributing-parent "
            f"count ({distinct}) — inputs are inconsistent"
        )
    silenced = None if total_parents is None else total_parents - distinct

    per_parent = tuple(
        ParentContribution(
            parent_id=pid,
            count=count,
            share=count / attributed_count,
        )
        for pid, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )

    max_count = per_parent[0].count
    max_share = max_count / attributed_count
    dominant_parent = per_parent[0].parent_id
    shares = [pc.share for pc in per_parent]
    balance_entropy = 0.0 if distinct == 1 else _normalized_entropy(shares)

    # Verdict precedence: unknown -> single_source -> dominated -> balanced -> skewed.
    if distinct == 1:
        verdict = "single_source"
    elif max_share >= dominance_threshold:
        verdict = "dominated"
    elif balance_entropy >= balance_entropy_threshold:
        verdict = "balanced"
    else:
        verdict = "skewed"

    notes_list: list[str] = []
    if silenced is not None and silenced > 0:
        notes_list.append(
            f"{silenced} of {total_parents} parents contributed nothing to the output"
        )
    if verdict == "single_source":
        notes_list.append("one parent voice — the merge is single-sourced")
    notes = tuple(notes_list)

    return MergeSourceBalanceReport(
        attributed_count=attributed_count,
        unattributed_count=unattributed_count,
        contributing_parent_count=distinct,
        silenced_parent_count=silenced,
        max_share=max_share,
        dominant_parent=dominant_parent,
        balance_entropy=balance_entropy,
        per_parent=per_parent,
        dominance_threshold=dominance_threshold,
        balance_entropy_threshold=balance_entropy_threshold,
        verdict=verdict,
        notes=notes,
    )
