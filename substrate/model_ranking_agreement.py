"""Model ranking-agreement axis — do two models rank the same tasks the same way?

Given two models' scores on a shared set of benchmark tasks, this axis measures the
RANK-ORDER agreement between them via **Kendall's tau-b**: *if model A finds task X harder than
task Y, does model B agree?* A high tau means the two models see the same difficulty landscape;
a low or negative tau means they disagree (or invert) it.

This is genuinely distinct machinery from the other cross-model / cross-task bench axes:

* ``task_redundancy`` (#1984) uses **Pearson VALUE-correlation** between two TASKS (are two tasks
  measuring the same thing?) — sensitive to score magnitude, requires interval scale.
* ``task_discrimination`` (#1960) measures inter-model **VARIANCE on ONE task** (does a single
  task separate models?) — a per-task spread.
* THIS axis uses **RANK (ordinal) correlation** across the WHOLE task set between TWO MODELS —
  robust to monotonic nonlinearity and score-scale differences (it sees only the ordering).

Pearson and Kendall can disagree: two models may have high value-correlation yet low
rank-agreement (a non-monotonic mapping), or vice versa. So the machinery is distinct, not a
re-labeling.

**Measured fields:**

* ``shared_task_count`` — tasks scored by BOTH models (the correlation is computed only over
  these; the intersection, never padded).
* ``dropped_from_a`` / ``dropped_from_b`` — tasks present in only one model (auditable mismatch;
  the operator sees what was excluded, not a silent failure). ``dropped_labels_a/b`` carry the
  actual labels sorted.
* ``concordant_pairs`` — task-pairs the two models ordered the same way (both nonzero, same sign).
* ``discordant_pairs`` — task-pairs the two models ordered oppositely.
* ``tie_pairs_a`` / ``tie_pairs_b`` — task-pairs tied within one model's scores (tau-b tie
  adjustment; the denominator corrects for these).
* ``kendall_tau`` — Kendall's tau-b in ``[-1.0, 1.0]`` (``1`` = identical ordering, ``-1`` =
  inverted, ``0`` = no systematic agreement). ``None`` when undefined (``< 2`` shared tasks, or
  one model ties on every pair so the denominator collapses).
* ``agreement_ratio`` = ``concordant / (concordant + discordant)`` — fraction of COMPARABLE pairs
  that agree (``None`` when no comparable pairs exist).
* ``rank_ordering_a`` / ``rank_ordering_b`` — the shared tasks ordered best-first by each model
  (ties broken by label asc for determinism; auditable: the operator sees the literal orderings,
  not a black-box coefficient).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero shared tasks -> ``unknown`` (nothing to correlate — defer, never fabricated).
* one shared task -> ``single_task`` (one item cannot be rank-correlated — honest base case
  distinct from ``unknown`` which has none).
* ``>= 2`` shared tasks but tau undefined (all-tie in one model) -> ``unmeasurable`` (defer — the
  ordering carries no signal; never fabricated ``independent``).
* ``kendall_tau >= concordance_threshold`` (default ``0.6``) -> ``concordant_ranking`` (models
  broadly agree on the difficulty ordering).
* ``kendall_tau <= discordance_threshold`` (default ``-0.6``) -> ``inverted_ranking`` (models
  systematically invert the ordering — strong, opposite, signal).
* otherwise -> ``independent_ranking`` (no systematic agreement or disagreement).

**DESCRIPTIVE NOT NORMATIVE:** ``concordant_ranking`` does NOT mean "good" — two models agreeing
may share the same blind spots (correlated failure, not quality). ``inverted_ranking`` does NOT
mean "bad" — divergent difficulty landscapes can be complementary (ensemble value). The operator
judges whether agreement reflects genuine capability alignment or correlated bias. This axis
surfaces the FACT of ordering agreement; it does not prescribe the right value.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero tasks are shared.
* ``single_task`` is its own honest base case (one item — distinct from ``unknown`` and from any
  correlation verdict). ``kendall_tau`` / ``agreement_ratio`` are ``None`` for it (defer).
* ``unmeasurable`` is its own honest state when tau is mathematically undefined (all-tie) — it is
  NOT collapsed into ``independent_ranking`` (a real measured near-zero tau).
* ``kendall_tau`` is ``None`` only for ``unknown`` / ``single_task`` / ``unmeasurable``; a real
  near-zero tau is carried as a measured ``0.0``, never deferred.
* dropped tasks are surfaced verbatim (``dropped_labels_a/b``) — the mismatch is auditable, never
  silently absorbed.
* tau-b (not tau-a): the tie-adjusted denominator makes the coefficient comparable across models
  with different tie rates; raw pair counts are still carried for audit.
* every ordering auditable via ``rank_ordering_a/b`` (literal task sequences — no black-box).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted inputs + reproducible output).
* import-free of off-main siblings (plain ``(label, score)`` pairs; route layer adapts 1:1 from
  the bench per-model-per-task score log).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ModelRankingAgreementReport",
    "measure_model_ranking_agreement",
]

_DEFAULT_CONCORDANCE_THRESHOLD = 0.60
_DEFAULT_DISCORDANCE_THRESHOLD = -0.60


@dataclass(frozen=True)
class ModelRankingAgreementReport:
    """The model ranking-agreement surface for one model pair. Advisory, pure."""

    shared_task_count: int
    dropped_from_a: int
    dropped_from_b: int
    dropped_labels_a: tuple[str, ...]
    dropped_labels_b: tuple[str, ...]
    concordant_pairs: int
    discordant_pairs: int
    tie_pairs_a: int
    tie_pairs_b: int
    kendall_tau: float | None
    agreement_ratio: float | None
    rank_ordering_a: tuple[str, ...]
    rank_ordering_b: tuple[str, ...]
    concordance_threshold: float
    discordance_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_model_ranking_agreement(
    scores_a: Sequence[tuple[str, float]],
    scores_b: Sequence[tuple[str, float]],
    *,
    concordance_threshold: float = _DEFAULT_CONCORDANCE_THRESHOLD,
    discordance_threshold: float = _DEFAULT_DISCORDANCE_THRESHOLD,
) -> ModelRankingAgreementReport:
    r"""Measure rank-order agreement between two models on shared tasks.

    ``scores_a`` / ``scores_b`` are ``(task_label, score)`` pairs for each model over a benchmark.
    Higher score is treated as better (rank 1 = highest score). The Kendall tau-b is computed only
    over tasks scored by BOTH models. Returns a :class:`ModelRankingAgreementReport`.

    Raises:
        ValueError: if a threshold is outside its valid range.
    """
    if not 0.0 < concordance_threshold <= 1.0:
        raise ValueError(
            f"concordance_threshold must be in (0.0, 1.0]; got {concordance_threshold}"
        )
    if not -1.0 <= discordance_threshold < 0.0:
        raise ValueError(
            f"discordance_threshold must be in [-1.0, 0.0); got {discordance_threshold}"
        )

    map_a: dict[str, float] = dict(scores_a)
    map_b: dict[str, float] = dict(scores_b)

    labels_a = set(map_a)
    labels_b = set(map_b)
    shared = sorted(labels_a & labels_b)
    dropped_a = sorted(labels_a - labels_b)
    dropped_b = sorted(labels_b - labels_a)
    shared_count = len(shared)

    dropped_from_a = len(dropped_a)
    dropped_from_b = len(dropped_b)

    rank_ordering_a = tuple(
        sorted(shared, key=lambda t: (-map_a[t], t))
    )
    rank_ordering_b = tuple(
        sorted(shared, key=lambda t: (-map_b[t], t))
    )

    def _base_report(
        verdict: str,
        notes: tuple[str, ...],
        *,
        tau: float | None,
        agreement: float | None,
        concordant: int,
        discordant: int,
        tie_a: int,
        tie_b: int,
    ) -> ModelRankingAgreementReport:
        return ModelRankingAgreementReport(
            shared_task_count=shared_count,
            dropped_from_a=dropped_from_a,
            dropped_from_b=dropped_from_b,
            dropped_labels_a=tuple(dropped_a),
            dropped_labels_b=tuple(dropped_b),
            concordant_pairs=concordant,
            discordant_pairs=discordant,
            tie_pairs_a=tie_a,
            tie_pairs_b=tie_b,
            kendall_tau=tau,
            agreement_ratio=agreement,
            rank_ordering_a=rank_ordering_a,
            rank_ordering_b=rank_ordering_b,
            concordance_threshold=concordance_threshold,
            discordance_threshold=discordance_threshold,
            verdict=verdict,
            notes=notes,
        )

    if shared_count == 0:
        return _base_report(
            "unknown",
            ("no shared tasks — ranking agreement unmeasurable",),
            tau=None,
            agreement=None,
            concordant=0,
            discordant=0,
            tie_a=0,
            tie_b=0,
        )

    if shared_count == 1:
        return _base_report(
            "single_task",
            ("one shared task — a single item cannot be rank-correlated",),
            tau=None,
            agreement=None,
            concordant=0,
            discordant=0,
            tie_a=0,
            tie_b=0,
        )

    concordant = 0
    discordant = 0
    tie_a = 0
    tie_b = 0
    for i in range(shared_count):
        for j in range(i + 1, shared_count):
            ai, aj = map_a[shared[i]], map_a[shared[j]]
            bi, bj = map_b[shared[i]], map_b[shared[j]]
            sa = 1 if ai > aj else -1 if ai < aj else 0
            sb = 1 if bi > bj else -1 if bi < bj else 0
            if sa == 0:
                tie_a += 1
            if sb == 0:
                tie_b += 1
            if sa != 0 and sb != 0:
                if sa == sb:
                    concordant += 1
                else:
                    discordant += 1

    n0 = shared_count * (shared_count - 1) // 2
    denom_sq = (n0 - tie_a) * (n0 - tie_b)
    comparable = concordant + discordant

    if denom_sq <= 0:
        return _base_report(
            "unmeasurable",
            ("tau undefined — one model ties on every pair (no ordering signal)",),
            tau=None,
            agreement=(concordant / comparable) if comparable > 0 else None,
            concordant=concordant,
            discordant=discordant,
            tie_a=tie_a,
            tie_b=tie_b,
        )

    tau = (concordant - discordant) / math.sqrt(denom_sq)
    agreement = concordant / comparable if comparable > 0 else None

    if tau >= concordance_threshold:
        verdict = "concordant_ranking"
        notes = (
            f"kendall_tau {tau:.4f} >= concordance_threshold {concordance_threshold:.2f} — "
            "models broadly agree on the difficulty ordering",
        )
    elif tau <= discordance_threshold:
        verdict = "inverted_ranking"
        notes = (
            f"kendall_tau {tau:.4f} <= discordance_threshold {discordance_threshold:.2f} — "
            "models systematically invert the ordering",
        )
    else:
        verdict = "independent_ranking"
        notes = (
            f"kendall_tau {tau:.4f} between thresholds — no systematic agreement or "
            "disagreement",
        )

    return _base_report(
        verdict,
        notes,
        tau=tau,
        agreement=agreement,
        concordant=concordant,
        discordant=discordant,
        tie_a=tie_a,
        tie_b=tie_b,
    )
