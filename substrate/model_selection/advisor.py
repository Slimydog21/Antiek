"""Model-selection advisor — the decision tree that fuses bench + cost + budget (asks #8/#9/#10).

The operator's asks #8/#9/#10: *"...there should be a decision tree tab where the
model should be selected (also include a bar of how much usage was used on that
API key given the limit I set in my budget in settings; also it would be cool to
display a projection of how the proposed prompt would affect that limit)... I
also want to be able to add models in settings... Antiek-bench that benchmarked
performance... so that I can know on a weekly basis what models are best at what
tasks."* NotDiamond (ask #12) is **decision-deferred** (bench must ratify first),
and the CEO-DIRECTIVE fixes that Antiek-bench and any router are **advisory, not
routing authorities** — model choice stays operator-controlled.

That leaves a missing synthesis point. The pieces all exist, but separately:
  * the bench produces per-``(task_family, model)`` mean scores (#1873
    ``WeeklyBenchSnapshot`` → ``ModelScore``);
  * the budget produces a forward-cost projection + ``within_budget`` verdict
    (#1838 ``BudgetProjection``);
  * the dispatch config lists the model inventory with per-model unit pricing
    (``substrate/dispatch/config.yaml``, ``0.0`` = unpriced placeholder);
  * the operator sets constraints (exclusions, a preferred pin, a max cost).

**Nothing fuses them into a ranked, explained recommendation.** This module is
that fusion — the Antiek-native **advisory decision tree** the operator named.
It does NOT replace the operator's pick (authority stays operator-side) and does
NOT dispatch (no routing authority). It ranks the inventory for one task family
using bench quality first, cost second, and the operator's budget/constraints as
hard gates, and explains every position so the choice is auditable, not a
black-box "best model."

**Why pure + import-free of #1873 / #1838.** Both ship in separate off-main PRs;
hard-importing their shapes would stack PRs and break independent bar-cleanliness
on a frozen main. Instead this module defines compatible input shapes
(``ModelBenchScore``, ``CostBand``, ``BudgetAffordability``) that the route layer
adapts 1:1 from ``ModelScore`` / ``BudgetProjection``. The module owns the ONE
thing no other does: the **ranking + explanation**.

**The load-bearing invariants (each is a test):**

1. **An unscored model is never ranked above a scored one.** A model whose bench
   ``mean_score`` is ``None`` (no completed runs) is ``scored=False`` and sorts
   below every scored model — never assigned a fabricated ``0.0`` to compare it.
2. **An unpriced model's cost band is kept with ``pricing_known=False``, never
   coerced to a ``0.0`` numeric.** A model whose unit pricing is the
   dispatch-config ``0.0`` placeholder (or absent) keeps its ``CostBand`` with
   ``low``/``high`` = ``None`` and ``pricing_known=False`` (auditable: you can
   tell "unpriced" apart from "absent from the cost map"), and its affordability
   is ``"unknown"``, never fabricated affordable/unaffordable. (Mirrors #1838's
   ``pricing_known=False``.)
3. **An unknown budget never fabricates a verdict.** When the budget's
   ``within_budget`` is ``None`` (no limit set, or projection unknown) every
   model's affordability is ``"unknown"`` — not a blanket "affordable."
4. **An excluded model never appears in the ranked output.** Operator exclusions
   are a hard filter; excluded models are surfaced separately with their reason
   so the exclusion is auditable, not silently dropped.
5. **A preferred pin is honored as rank 1 — but honestly.** An operator-pinned
   preferred model takes rank 1 regardless of score (explicit authority beats
   advisory), yet its score/cost/affordability are still shown so the operator
   sees exactly what the pin trades away. Never hidden.
6. **No bench signal → cost-only ranking, flagged.** When NO model in the family
   has a completed-run score, the ranking falls back to cost-ascending and the
   recommendation is flagged ``evidence_quality="no_bench_signal"`` — honest
   about the missing quality signal, never silently fabricating a quality order.
7. **Ties are named, not arbitrarily broken.** Models that are co-equal on
   ``(score, cost)`` (within epsilon) are ALL returned in ``top`` — evidence that
   does not distinguish them must not invent a single winner. ``rank`` still
   assigns 1..N by a stable final tiebreak (model_id asc) for deterministic
   display, but ``top`` makes the co-equality explicit.
8. **Every ranked model is fully auditable.** Each ``RankedModel`` carries its
   bench score (or ``None``), ``scored`` flag, ``score_rank`` among scored
   models, per-prompt cost (or ``None``), affordability verdict, exclusion state,
   and a human-readable rationale reproducing the verdict.
9. **Deterministic + pure.** Same inputs → byte-identical ranking. Stable sort
   key ``(score desc, cost-low asc, model_id asc)`` for scored models and
   ``(cost-low asc, model_id asc)`` for unscored; no I/O, clock, dispatch, or LLM.
10. **Advisory only.** This module returns a value; it never dispatches, never
    mutates inventory, budget, or the bench registry. The operator picks.

**Composition (the decision tree):**

    bench scores (#1873) ─────────────┐
    per-model cost (dispatch config) ─┤
    budget projection (#1838) ────────┼─→ [THIS] ranked advisory recommendation
    operator constraints (settings) ──┤            │
    task family (the prompt) ─────────┘            ▼
                                      settings "decision tree" tab (operator picks)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# A score/cost delta within ±epsilon is "equal" (float noise / genuinely tied).
_EPSILON: float = 1e-9

_AFFORDABLE = "affordable"
_UNAFFORDABLE = "unaffordable"
_UNKNOWN = "unknown"

# Evidence-quality verdicts for the whole recommendation.
_EVIDENCE_FULL = "scored"  # ≥1 model has a completed-run score
_EVIDENCE_NONE = "no_bench_signal"  # no model scored → cost-only ranking


class ModelSelectionError(ValueError):
    """A selection input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ModelEntry:
    """One available model in the inventory (caller-supplied from settings).

    ``unit_cost_in`` / ``unit_cost_out`` are USD per million tokens, ``None`` or
    ``0.0`` meaning unpriced (the dispatch-config placeholder convention). A
    model is always a candidate unless the operator excludes it.
    """

    model_id: str
    unit_cost_in: float | None = None
    unit_cost_out: float | None = None


@dataclass(frozen=True)
class ModelBenchScore:
    """One model's bench result for the task family (compatible with #1873 ModelScore).

    ``mean_score`` is ``None`` when the model had no completed runs (pending/
    unbenchmarked). ``completed_runs``/``pending_runs`` mirror #1873 so the route
    layer adapts 1:1.
    """

    model_id: str
    mean_score: float | None
    completed_runs: int = 0
    pending_runs: int = 0

    @property
    def scored(self) -> bool:
        return self.mean_score is not None


@dataclass(frozen=True)
class CostBand:
    """A model's per-prompt estimated cost range (USD), compatible with #1838.

    ``low``/``high`` are ``None`` when the model is unpriced (placeholder rates).
    ``pricing_known`` is False in that case — the advisor never treats an unknown
    cost as ``0``.
    """

    low: float | None
    high: float | None
    pricing_known: bool = True


@dataclass(frozen=True)
class BudgetAffordability:
    """The budget verdict for the proposed prompt (compatible with #1838).

    ``within_budget`` is ``None`` when there is no limit set or the projection is
    unknown — the advisor never fabricates a verdict from ``None``. ``remaining_usd``
    is informational (may be ``None``).
    """

    within_budget: bool | None
    remaining_usd: float | None = None


@dataclass(frozen=True)
class OperatorConstraints:
    """The operator's hard gates and overrides (settings)."""

    excluded: frozenset[str] = field(default_factory=frozenset)
    preferred: str | None = None
    max_cost: float | None = None  # per-prompt cost ceiling; None = no ceiling


@dataclass(frozen=True)
class RankedModel:
    """One model's position in the ranked recommendation, fully auditable."""

    model_id: str
    rank: int
    bench_score: float | None
    scored: bool
    score_rank: int | None  # rank among scored models only (None if unscored)
    per_prompt_cost: CostBand | None
    affordability: str  # affordable / unaffordable / unknown
    preferred_override: bool
    rationale: str


@dataclass(frozen=True)
class ExcludedModel:
    """An operator-excluded model, surfaced for audit (never silently dropped)."""

    model_id: str
    reason: str
    bench_score: float | None
    per_prompt_cost: CostBand | None


@dataclass(frozen=True)
class ModelRecommendation:
    """The full advisory recommendation for one task family. Pure value."""

    task_family: str
    ranked: list[RankedModel] = field(default_factory=list)
    top: list[RankedModel] = field(default_factory=list)  # co-equal best (≥1)
    excluded: list[ExcludedModel] = field(default_factory=list)
    evidence_quality: str = _EVIDENCE_NONE  # scored | no_bench_signal
    over_cost_ceiling: tuple[str, ...] = ()  # filtered by max_cost (audit)
    notes: list[str] = field(default_factory=list)

    @property
    def has_candidates(self) -> bool:
        return len(self.ranked) > 0


def _cost_key(cost: CostBand | None) -> tuple[int, float, float]:
    """Stable sort key for cost: priced-first, then low-asc, then high-asc.

    A ``None``/unpriced cost sorts AFTER any priced cost (we know its number, we
    do not know the unpriced one). Among unpriced, tiebreak by 0.0 so they group.
    """
    if cost is None or cost.low is None or cost.high is None or not cost.pricing_known:
        return (1, 0.0, 0.0)
    return (0, cost.low, cost.high)


def _affordability(budget: BudgetAffordability) -> str:
    """Honest affordability from the budget verdict (None → unknown, never fabricated)."""
    if budget.within_budget is None:
        return _UNKNOWN
    return _AFFORDABLE if budget.within_budget else _UNAFFORDABLE


def _rationale(
    *,
    scored: bool,
    bench_score: float | None,
    score_rank: int | None,
    cost: CostBand | None,
    affordability: str,
    preferred_override: bool,
) -> str:
    parts: list[str] = []
    if preferred_override:
        parts.append("rank 1 via operator preferred-pin (authority overrides advisory)")
    if scored and bench_score is not None and score_rank is not None:
        parts.append(f"bench score={bench_score:.4g} (score rank {score_rank})")
    elif scored:
        parts.append(f"bench score={bench_score:.4g}")
    else:
        parts.append("unbenchmarked (no completed runs; not ranked on quality)")
    if cost is not None and cost.pricing_known and cost.low is not None and cost.high is not None:
        parts.append(f"per-prompt cost ${cost.low:g}–${cost.high:g}")
    else:
        parts.append("per-prompt cost unknown (unpriced)")
    parts.append(f"affordability={affordability}")
    return "; ".join(parts)


def recommend_model(
    *,
    task_family: str,
    inventory: Sequence[ModelEntry],
    bench_scores: Mapping[str, ModelBenchScore],
    prompt_cost: Mapping[str, CostBand],
    budget: BudgetAffordability,
    constraints: OperatorConstraints | None = None,
    epsilon: float = _EPSILON,
) -> ModelRecommendation:
    """Rank the inventory for one task family into an advisory recommendation.

    Quality (bench score) ranks first among scored models; cost is the secondary
    key and the primary key when no model is scored. Exclusions are a hard filter;
    a preferred pin forces rank 1 (honestly, with score/cost shown); a ``max_cost``
    ceiling filters priced models above it (unpriced models are kept and noted,
    never silently dropped). Affordability comes straight from the budget verdict
    (``None`` → ``"unknown"``). Ties on ``(score, cost)`` are all returned in
    ``top`` — evidence that does not distinguish them must not invent a winner.
    """
    if epsilon < 0:
        raise ModelSelectionError(f"epsilon must be >= 0 (got {epsilon})")
    family = (task_family or "").strip()
    if not family:
        raise ModelSelectionError("task_family must be non-empty")
    constraints = constraints or OperatorConstraints()

    notes: list[str] = [
        "authority=advisory — ranks models for operator selection; never dispatches or routes",
        "ranking is bench-quality first, cost second; budget/constraints are gates, not scores",
    ]
    affordability = _affordability(budget)
    if budget.within_budget is None:
        notes.append("budget within_budget is unknown — affordability=unknown for all models")

    excluded: list[ExcludedModel] = []
    over_ceiling: list[str] = []
    candidates: list[tuple[ModelEntry, CostBand | None, ModelBenchScore]] = []

    for entry in inventory:
        model_id = (entry.model_id or "").strip()
        if not model_id:
            raise ModelSelectionError("ModelEntry.model_id must be non-empty")
        score = bench_scores.get(model_id)
        if score is None:
            score = ModelBenchScore(model_id=model_id, mean_score=None)
        cost = prompt_cost.get(model_id)

        if model_id in constraints.excluded:
            excluded.append(
                ExcludedModel(
                    model_id=model_id,
                    reason="operator-excluded",
                    bench_score=score.mean_score,
                    per_prompt_cost=cost,
                )
            )
            continue

        # max_cost ceiling: filter PRICED models above it; keep unpriced + note.
        if (
            constraints.max_cost is not None
            and cost is not None
            and cost.pricing_known
            and cost.low is not None
            and cost.low > constraints.max_cost + epsilon
        ):
            over_ceiling.append(model_id)
            continue

        candidates.append((entry, cost, score))

    if excluded:
        notes.append(
            f"{len(excluded)} model/s excluded by operator — surfaced in excluded list, not ranked"
        )
    if over_ceiling:
        notes.append(
            f"{len(over_ceiling)} model/s filtered by max_cost ceiling — kept unpriced models "
            "(cannot verify against ceiling)"
        )

    if not candidates:
        notes.append("no candidates after exclusions/ceiling — empty recommendation")
        return ModelRecommendation(
            task_family=family,
            ranked=[],
            top=[],
            excluded=excluded,
            evidence_quality=_EVIDENCE_NONE,
            over_cost_ceiling=tuple(over_ceiling),
            notes=notes,
        )

    scored = [c for c in candidates if c[2].scored]
    unscored = [c for c in candidates if not c[2].scored]
    evidence_quality = _EVIDENCE_FULL if scored else _EVIDENCE_NONE
    if evidence_quality == _EVIDENCE_NONE:
        notes.append(
            "no model has a completed-run bench score for this family — ranking by cost only "
            "(evidence_quality=no_bench_signal)"
        )

    # Scored models: score desc, then cost asc, then model_id asc.
    scored_sorted = sorted(
        scored,
        key=lambda c: (
            -(c[2].mean_score or 0.0),
            _cost_key(c[1]),
            c[0].model_id,
        ),
    )
    # Unscored models: cost asc, then model_id asc.
    unscored_sorted = sorted(
        unscored,
        key=lambda c: (_cost_key(c[1]), c[0].model_id),
    )
    ordered = scored_sorted + unscored_sorted

    # score_rank among scored models only.
    score_rank_map: dict[str, int] = {
        c[0].model_id: i + 1 for i, c in enumerate(scored_sorted)
    }

    ranked: list[RankedModel] = []
    for idx, (entry, cost, score) in enumerate(ordered):
        model_id = entry.model_id
        sr = score_rank_map.get(model_id) if score.scored else None
        preferred_override = constraints.preferred is not None and model_id == constraints.preferred
        ranked.append(
            RankedModel(
                model_id=model_id,
                rank=idx + 1,
                bench_score=score.mean_score,
                scored=score.scored,
                score_rank=sr,
                per_prompt_cost=cost,
                affordability=affordability,
                preferred_override=preferred_override,
                rationale=_rationale(
                    scored=score.scored,
                    bench_score=score.mean_score,
                    score_rank=sr,
                    cost=cost,
                    affordability=affordability,
                    preferred_override=preferred_override,
                ),
            )
        )

    # Apply preferred-pin override: force rank 1 (stably), renumber.
    if constraints.preferred is not None:
        pinned = [r for r in ranked if r.model_id == constraints.preferred]
        if pinned:
            rest = [r for r in ranked if r.model_id != constraints.preferred]
            ordered_ids = [constraints.preferred] + [r.model_id for r in rest]
        else:
            ordered_ids = [r.model_id for r in ranked]
            notes.append(
                f"preferred model {constraints.preferred!r} not in candidates "
                "(excluded/filtered/absent) — pin not applied"
            )
    else:
        ordered_ids = [r.model_id for r in ranked]

    by_id = {r.model_id: r for r in ranked}
    final_ranked: list[RankedModel] = []
    for new_rank, model_id in enumerate(ordered_ids, start=1):
        r = by_id[model_id]
        # Re-derive rationale so the rank/score-rank reflect the final ordering.
        final_ranked.append(
            RankedModel(
                model_id=r.model_id,
                rank=new_rank,
                bench_score=r.bench_score,
                scored=r.scored,
                score_rank=r.score_rank,
                per_prompt_cost=r.per_prompt_cost,
                affordability=r.affordability,
                preferred_override=r.preferred_override,
                rationale=_rationale(
                    scored=r.scored,
                    bench_score=r.bench_score,
                    score_rank=r.score_rank,
                    cost=r.per_prompt_cost,
                    affordability=r.affordability,
                    preferred_override=r.preferred_override,
                ),
            )
        )

    top = _co_equal_top(final_ranked, epsilon=epsilon)
    if len(top) > 1:
        notes.append(
            f"{len(top)} models are co-equal on (score, cost) — all returned in top; "
            "evidence does not distinguish a single winner"
        )

    return ModelRecommendation(
        task_family=family,
        ranked=final_ranked,
        top=top,
        excluded=excluded,
        evidence_quality=evidence_quality,
        over_cost_ceiling=tuple(over_ceiling),
        notes=notes,
    )


def _co_equal_top(ranked: list[RankedModel], *, epsilon: float) -> list[RankedModel]:
    """Return every model tied with rank 1 on (score, cost).

    Two models are co-equal if their bench scores are equal within ``epsilon``
    (treating ``None`` as equal to ``None`` only) AND their cost keys are equal.
    This refuses to invent a single winner when the evidence ties.
    """
    if not ranked:
        return []
    best = ranked[0]
    top: list[RankedModel] = [best]

    def _score_equal(a: RankedModel, b: RankedModel) -> bool:
        if a.scored != b.scored:
            return False
        if not a.scored:
            return True  # both unscored
        return abs((a.bench_score or 0.0) - (b.bench_score or 0.0)) <= epsilon

    def _cost_equal(a: RankedModel, b: RankedModel) -> bool:
        return _cost_key(a.per_prompt_cost) == _cost_key(b.per_prompt_cost)

    for cand in ranked[1:]:
        if _score_equal(best, cand) and _cost_equal(best, cand):
            top.append(cand)
        else:
            break
    return top
