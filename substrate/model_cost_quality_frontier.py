r"""Model cost-quality frontier — which models are Pareto-efficient per task?

Operator vision (asks #8, #9, #11): *"create a benchmark called Antiek-bench that
benchmarked performance ... so that I can know on a weekly basis what models are best
at what tasks"* combined with *"a bar of how much usage has been used on that API key
given the limit I set in my budget."* The operator wants to optimize model choice for
VALUE — quality delivered per dollar — not quality in a vacuum. A model that scores
0.95 at \$1.00/call may be a worse VALUE pick than one scoring 0.93 at \$0.05/call
(19x cheaper for 2% less quality). The PARETO FRONTIER answers exactly this: which
models are NOT dominated — no other model is both CHEAPER AND at-least-as-good. A model
off the frontier is strictly wasting money (a cheaper-or-equal alternative is at least
as good). This is the value-optimization lens the operator needs to pick models that
respect the budget without leaving quality on the table.

**Genuinely distinct from the bench/model surface (load-bearing):**

* ``model_fit_for_task`` (#1970): was the CHOSEN model the best/nearest by PURE QUALITY
  (chosen_score vs best_score, rank, relative_gap). It has NO cost dimension — it cannot
  see that the top-quality model is 20x more expensive than a 2%-worse alternative. THIS
  measures the COST-QUALITY tradeoff across ALL scored models for a task and identifies the
  non-dominated set. Different input (adds cost), different computation (Pareto dominance
  vs rank), different decision (which models offer the best value tradeoff vs was the pick
  top-quality).
* ``task_discrimination`` (#1960): does the task SEPARATE models (is there quality variance
  at all). THIS assumes quality variance exists and asks which of the variants are
  value-efficient. A task can discriminate strongly (high variance) yet have every model on
  the frontier (all trade off cost/quality uniquely).
* ``model_ranking_agreement`` (#2009): do two models AGREE on task ordering (Kendall tau).
  THIS measures agreement among benchmark RESULTS for one task — completely orthogonal.
* ``ceiling_accuracy`` (#1968): did the RECOMMENDED cost ceiling match actual (backward
  cost calibration). THIS is forward value optimization — which models are worth their cost
  going forward.
* ``bench_difficulty_coverage`` / ``task_novelty`` / ``rewrite_quality``: structural
  benchmark-health axes (difficulty spread, evolution, rewrite success) — none measures the
  per-model cost-quality efficiency frontier.

**The measurement (hard to vary).** The classic **Pareto dominance** relation over the
(cost, quality) plane. For two models A, B scored on the same task:

    A dominates B  iff  (A.quality >= B.quality AND A.cost <= B.cost)
                        AND (A.quality > B.quality OR A.cost < B.cost)

A model is **Pareto-efficient (on the frontier)** iff NO other scored model dominates it.
The frontier is the set of models where you cannot improve one axis without sacrificing
the other — these are the only models a value-conscious operator should ever pick. Every
model OFF the frontier is **dominated**: a cheaper-or-equal alternative is at least as good,
so picking it wastes budget for zero quality gain.

**Key properties (load-bearing):**

* Pareto dominance is a PARTIAL ORDER (not total) — models can be incomparable (A cheaper
  but lower quality, B pricier but higher quality). Incomparable models are BOTH on the
  frontier. This is why the frontier can have many members — it is the set of all
  incomparable best-tradeoff points, not a single winner.
* Ties on BOTH axes (identical cost AND quality) dominate NEITHER: a strict inequality is
  required on at least one axis. So duplicate benchmark entries do not spuriously dominate
  each other.
* ``effective_choice_count`` (frontier size) answers *"how many genuinely-distinct value
  options exist?"* — 1 means a single model strictly dominates on value (a clear winner);
  many means the task has a real cost-quality tradeoff the operator must judge.
* ``dominated_models`` carries the auditable waste set: each dominated model plus WHICH
  models dominate it (so the operator sees exactly what cheaper-or-equal alternative beats
  it). This is the actionable budget signal.

**Measured fields:**

* ``task_id`` / ``model_count`` (models scored for the task).
* ``frontier_size`` / ``frontier_share`` — count and fraction of Pareto-efficient models.
* ``frontier_models`` — every ``(model_id, quality_score, cost_per_call)`` on the frontier,
  sorted by quality desc then cost asc then id asc (auditable: the value-optimal set).
* ``dominated_count`` / ``dominated_models`` — the waste set, each with
  ``dominating_model_ids`` (auditable: who beats it, and on what value).
* ``cheapest_frontier_model`` / ``highest_quality_frontier_model`` — the two extremes of the
  frontier (the budget anchor and the quality anchor).
* ``value_spread`` — ``max_frontier_cost / min_frontier_cost`` (the cost range the frontier
  spans; ``None`` when only one frontier member or zero-cost floor — never divide by zero).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero models scored -> ``unknown`` (defer — frontier undefined, never fabricated).
* exactly one model -> ``single_candidate`` (trivially on the frontier — no alternative to
  compare against).
* ``>= 2`` models, ``frontier_size == model_count`` -> ``fully_efficient`` (every model
  trades off uniquely — no dominated waste; honest ``frontier_share == 1.0``).
* ``frontier_size == 1`` (out of ``>= 2``) -> ``single_survivor`` (one model strictly
  dominates all others on value — a clear winner; the strongest value-concentration signal).
* ``1 < frontier_size < model_count`` -> ``partial_frontier`` (some models dominate, some
  are dominated — a typical mixed picture; the operator culls the dominated set).

**DESCRIPTIVE NOT NORMATIVE:** ``single_survivor`` does NOT mean "pick it blindly" — the
survivor dominates on the (cost, quality) axes the benchmark measures, but quality here is
a benchmark score, not the operator's full judgment of fit, latency, or feature support
(NotDiamond #439/#470 and the decision-tree composition layer #1972 cover the richer
routing decision). ``fully_efficient`` does NOT mean "bad" — it means the task has a
genuine cost-quality tradeoff with no free lunch. The operator judges which frontier point
matches the moment's budget/quality priority.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates — frontier fields are ``None`` when no model is scored.
* ``single_candidate`` is an honest base case (frontier_size 1 by default, share 1.0) —
  distinct from ``unknown`` (deferred, ``None``) and from ``single_survivor`` (1 survivor
  out of ``>= 2`` — a real dominance result).
* ``frontier_share`` is in ``[0, 1]``; ``dominated_count = model_count - frontier_size``
  always holds (a verifiable partition).
* ``dominated_models.dominating_model_ids`` is the auditable evidence (who beats each
  dominated model — no black-box verdict).
* ``cost_per_call >= 0`` (a free model is a valid, strong frontier anchor); zero-cost
  duplicates handled without spurious domination.
* ``value_spread`` is ``None`` when the cost floor is 0 (would divide by zero) or when the
  frontier has one member — never a fabricated ``inf``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock, no
  mutation.
* ``authority`` is always ``"advisory"``; import-free of off-main siblings (plain
  ``ModelTaskCostQuality`` inputs; route layer adapts 1:1 from the bench runner's per-task
  results).

**Why Pareto and not a single value-score (e.g. quality/cost).** A ratio collapses the
two-dimensional tradeoff into one number, HIDING the structure the operator needs: it
cannot show that two models are incomparable (both worth considering), nor which SPECIFIC
models are dominated by which. Pareto dominance preserves the full tradeoff geometry and
surfaces the exact actionable signal (cull the dominated set). A ratio is lossy; the
frontier is the hard-to-vary, information-complete answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "DominatedModel",
    "FrontierModel",
    "ModelCostQualityFrontierError",
    "ModelCostQualityFrontierReport",
    "ModelTaskCostQuality",
    "measure_model_cost_quality_frontier",
]


@dataclass(frozen=True)
class ModelTaskCostQuality:
    """One model's benchmark result for one task: quality + cost (the two Pareto axes)."""

    model_id: str
    quality_score: float  # in [0.0, 1.0]
    cost_per_call: float  # >= 0.0 (cost units, e.g. USD cents)


@dataclass(frozen=True)
class FrontierModel:
    """One Pareto-efficient model (on the value frontier). Auditable."""

    model_id: str
    quality_score: float
    cost_per_call: float


@dataclass(frozen=True)
class DominatedModel:
    """A model off the frontier (a value-wasting pick). Auditable.

    ``dominating_model_ids`` is every model that is both cheaper-or-equal AND
    at-least-as-good (with a strict edge on one axis) — the exact alternatives the
    operator should pick instead.
    """

    model_id: str
    quality_score: float
    cost_per_call: float
    dominating_model_ids: tuple[str, ...]


@dataclass(frozen=True)
class ModelCostQualityFrontierReport:
    """The cost-quality Pareto frontier for one task's scored models. Advisory, pure."""

    task_id: str
    model_count: int
    frontier_size: int
    frontier_share: float | None  # frontier_size/model_count; None when unknown
    dominated_count: int
    frontier_models: tuple[FrontierModel, ...]
    dominated_models: tuple[DominatedModel, ...]
    cheapest_frontier_model: str | None
    highest_quality_frontier_model: str | None
    value_spread: float | None  # max/min frontier cost; None when 1 member or zero floor
    verdict: str  # unknown | single_candidate | fully_efficient | single_survivor | partial_frontier
    notes: tuple[str, ...]
    authority: str = "advisory"


class ModelCostQualityFrontierError(ValueError):
    """A model-cost-quality-frontier input violates a load-bearing invariant."""


def _dominates(a: ModelTaskCostQuality, b: ModelTaskCostQuality) -> bool:
    """True iff model A Pareto-dominates model B (cheaper-or-equal AND at-least-as-good,
    with a strict edge on at least one axis). Ties on BOTH axes dominate neither."""
    a_better_or_equal_quality = a.quality_score >= b.quality_score
    a_cheaper_or_equal = a.cost_per_call <= b.cost_per_call
    strict_edge = a.quality_score > b.quality_score or a.cost_per_call < b.cost_per_call
    return a_better_or_equal_quality and a_cheaper_or_equal and strict_edge


def measure_model_cost_quality_frontier(
    scored: Sequence[ModelTaskCostQuality],
    task_id: str,
) -> ModelCostQualityFrontierReport:
    """Measure the cost-quality Pareto frontier for one task's benchmarked models.

    ``scored`` are the ``(model_id, quality_score, cost_per_call)`` results for one task.
    Returns a :class:`ModelCostQualityFrontierReport` with the Pareto-efficient set and the
    dominated (value-wasting) set.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    tid = task_id.strip()
    if not tid:
        raise ModelCostQualityFrontierError(
            "task_id must be a non-empty string"
        )
    for entry in scored:
        if not 0.0 <= entry.quality_score <= 1.0:
            raise ModelCostQualityFrontierError(
                f"quality_score must be in [0.0, 1.0], got {entry.quality_score!r} "
                f"for model {entry.model_id!r}"
            )
        if entry.cost_per_call < 0.0:
            raise ModelCostQualityFrontierError(
                f"cost_per_call must be >= 0.0, got {entry.cost_per_call!r} "
                f"for model {entry.model_id!r}"
            )
        if not entry.model_id.strip():
            raise ModelCostQualityFrontierError(
                "model_id must be a non-empty string"
            )

    model_count = len(scored)

    if model_count == 0:
        return ModelCostQualityFrontierReport(
            task_id=tid,
            model_count=0,
            frontier_size=0,
            frontier_share=None,
            dominated_count=0,
            frontier_models=(),
            dominated_models=(),
            cheapest_frontier_model=None,
            highest_quality_frontier_model=None,
            value_spread=None,
            verdict="unknown",
            notes=(
                "no models scored for this task; the cost-quality frontier is not "
                "measurable (defer — never fabricated)",
            ),
        )

    if model_count == 1:
        sole = scored[0]
        return ModelCostQualityFrontierReport(
            task_id=tid,
            model_count=1,
            frontier_size=1,
            frontier_share=1.0,
            dominated_count=0,
            frontier_models=(
                FrontierModel(
                    model_id=sole.model_id,
                    quality_score=sole.quality_score,
                    cost_per_call=sole.cost_per_call,
                ),
            ),
            dominated_models=(),
            cheapest_frontier_model=sole.model_id,
            highest_quality_frontier_model=sole.model_id,
            value_spread=None,
            verdict="single_candidate",
            notes=(
                "one model scored — trivially on the frontier (no alternative to "
                "compare against); value-efficiency is not measurable, only trivial",
            ),
        )

    entries = list(scored)

    efficient_flags: list[bool] = []
    dominators: list[list[str]] = []
    for i, candidate in enumerate(entries):
        is_dominated = False
        cand_dominators: list[str] = []
        for j, other in enumerate(entries):
            if i == j:
                continue
            if _dominates(other, candidate):
                is_dominated = True
                cand_dominators.append(other.model_id)
        efficient_flags.append(not is_dominated)
        dominators.append(sorted(set(cand_dominators)))

    frontier_entries = [
        entries[i] for i in range(model_count) if efficient_flags[i]
    ]
    frontier_sorted = sorted(
        frontier_entries,
        key=lambda e: (-e.quality_score, e.cost_per_call, e.model_id),
    )
    frontier_models = tuple(
        FrontierModel(
            model_id=e.model_id,
            quality_score=e.quality_score,
            cost_per_call=e.cost_per_call,
        )
        for e in frontier_sorted
    )

    dominated_models = tuple(
        DominatedModel(
            model_id=e.model_id,
            quality_score=e.quality_score,
            cost_per_call=e.cost_per_call,
            dominating_model_ids=tuple(
                sorted(set(dominators[i]))
            ),
        )
        for i, e in enumerate(entries)
        if not efficient_flags[i]
    )

    frontier_size = len(frontier_models)
    dominated_count = model_count - frontier_size
    frontier_share = frontier_size / model_count

    cheapest = min(frontier_entries, key=lambda e: (e.cost_per_call, e.model_id))
    highest_q = max(frontier_entries, key=lambda e: (e.quality_score, e.model_id))
    min_cost = min(e.cost_per_call for e in frontier_entries)
    max_cost = max(e.cost_per_call for e in frontier_entries)
    value_spread = max_cost / min_cost if min_cost > 0.0 else None

    if frontier_size == model_count:
        verdict = "fully_efficient"
    elif frontier_size == 1:
        verdict = "single_survivor"
    else:
        verdict = "partial_frontier"

    notes: list[str] = [
        "model cost-quality frontier measures Pareto efficiency per task — which models "
        "are NOT dominated (no other is both cheaper AND at-least-as-good); a model off "
        "the frontier is a value-wasting pick (a cheaper-or-equal alternative is at least "
        "as good); model_fit #1970 checks PURE quality rank (no cost), this adds the cost "
        "dimension the budget-conscious operator needs",
        "Pareto dominance is a PARTIAL ORDER — incomparable models are BOTH on the "
        "frontier (a cheaper-lower-quality model and a pricier-higher-quality one neither "
        "dominates the other); ties on both axes dominate NEITHER (strict edge required); "
        "dominated_models carries who beats each waste pick — the actionable budget signal",
    ]
    if verdict == "fully_efficient":
        notes.append(
            f"all {model_count} model(s) are Pareto-efficient — every model trades off "
            f"cost/quality uniquely (frontier_share 1.0); no dominated waste, a genuine "
            f"tradeoff the operator must judge by current budget/quality priority"
        )
    elif verdict == "single_survivor":
        survivor = frontier_models[0].model_id
        notes.append(
            f"one survivor '{survivor}' dominates all {dominated_count} other model(s) "
            f"on value — a clear winner (frontier_share {frontier_share:.0%}); every "
            f"other model is a value-wasting pick"
        )
    else:
        notes.append(
            f"partial frontier: {frontier_size} of {model_count} model(s) "
            f"Pareto-efficient (frontier_share {frontier_share:.0%}), "
            f"{dominated_count} dominated (value-wasting — cull them); "
            f"value_spread {value_spread if value_spread is None else round(value_spread, 2)} "
            f"across the frontier's cost range"
        )

    return ModelCostQualityFrontierReport(
        task_id=tid,
        model_count=model_count,
        frontier_size=frontier_size,
        frontier_share=frontier_share,
        dominated_count=dominated_count,
        frontier_models=frontier_models,
        dominated_models=dominated_models,
        cheapest_frontier_model=cheapest.model_id,
        highest_quality_frontier_model=highest_q.model_id,
        value_spread=value_spread,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )
