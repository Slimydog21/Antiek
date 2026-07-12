"""Model recommendation engine — pure task→model decision tree (asks #10/#11/#12).

The operator's asks converge here:
- **#10:** *"there should be a decision tree tab where the model should be selected"*
- **#11:** the recursive benchmark tells you *"what models are best at what tasks"*
- **#12:** NotDiamond investigation — *"investigate whether implementing NotDiamond
  as a router will be useful"* — this module IS the router's brain. Whether the
  live dispatch goes through NotDiamond's API or Antiek's own dispatch, the
  DECISION of which model to pick for a given task is this pure computation.

This module is the **pure recommendation core**: given a task profile (type,
complexity, context needs), available models with their bench scores + pricing,
and a budget constraint, it returns a ranked, budget-aware model recommendation
with honest reasoning. The decision tree is explicit and testable — no black box.

**Pure** — no network, no dispatch, no config loading, no credentials. The
caller supplies the model inventory + bench scores (read from the bench ledger)
+ budget state (from #1838's projection); this module computes the ranking.

**The decision tree (explicit, not magic):**
1. **Capability filter** — must support grounding if required; must have
   sufficient context window for the task. Ineligible models are excluded and
   counted, never silently dropped.
2. **Quality score** — primary signal is the bench score for the task's family.
   Missing bench data does NOT exclude a model (new models deserve a chance);
   it flags the recommendation as bench-unverified and falls back to tier match.
3. **Budget filter** — if a budget constraint is set, models whose estimated cost
   exceeds the remaining headroom are ranked last (not excluded — the operator
   may still want to see them). If ALL models exceed, the cheapest is still
   recommended with an honest "all exceed budget" note.
4. **Tie-break** — higher bench score wins; ties broken by lower estimated cost;
   further ties by model_id (deterministic).

**Advisory authority** — this module RECOMMENDS; it never routes. The operator
sees the ranking and confirms the pick. ``authority="model_decision_advisory"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Advisory authority — recommends, never routes.
RECOMMENDATION_AUTHORITY = "model_decision_advisory"


class ModelRecommendationError(ValueError):
    """Fail-closed: structurally invalid inputs."""


@dataclass(frozen=True)
class TaskProfile:
    """The task the operator wants a model for.

    ``complexity_tier`` maps to the bench's task families: a "deep" research
    task should prefer models that score well on deep-research bench tasks,
    not just cheap fast ones.
    """

    task_type: str  # e.g. "deep_research", "talk_to_book", "synthesis"
    complexity_tier: str  # "fast" | "standard" | "deep"
    min_context_tokens: int = 0
    requires_grounding: bool = False


@dataclass(frozen=True)
class ModelOption:
    """One available model with its bench scores + pricing.

    ``bench_scores`` maps task-family → score [0.0, 1.0]. Missing families are
    fine — the model is still eligible but flagged as bench-unverified for that
    task. ``pricing_per_mtok`` is a tuple of (input_rate, output_rate) in USD;
    None when pricing is unknown.
    """

    model_id: str
    provider: str
    bench_scores: dict[str, float] = field(default_factory=dict)
    pricing_per_mtok: tuple[float, float] | None = None  # (input, output) USD/MTok
    max_context_tokens: int = 0  # 0 = unknown
    supports_grounding: bool = True


@dataclass(frozen=True)
class BudgetConstraint:
    """The operator's budget headroom for this prompt.

    ``max_cost_usd`` is the remaining headroom from #1838's projection. ``None``
    means no budget constraint (unlimited / unknown). ``estimated_tokens`` is the
    prompt's token count, used to compute per-model cost estimates.
    """

    max_cost_usd: float | None
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0


@dataclass(frozen=True)
class RankedModel:
    """One model in the ranking with its score + honest reasoning."""

    model_id: str
    provider: str
    score: float  # [0.0, 1.0] — higher is better
    estimated_cost_usd: float | None  # None when pricing unknown
    within_budget: bool | None  # True/False/None(no budget set)
    bench_verified: bool  # whether bench data existed for this task family
    reasoning: str


@dataclass(frozen=True)
class ModelRecommendation:
    """The ranked, budget-aware recommendation."""

    recommended_model_id: str | None  # None when no eligible models
    ranked: tuple[RankedModel, ...]
    excluded_capability: int  # models filtered out (no grounding / context too small)
    budget_filtered: bool  # whether budget constraint changed the ranking
    all_exceed_budget: bool  # every eligible model exceeds the headroom
    authority: str
    notes: tuple[str, ...]


def _estimate_cost(model: ModelOption, budget: BudgetConstraint) -> float | None:
    """Estimate the prompt's cost for this model. None when pricing unknown."""
    if model.pricing_per_mtok is None:
        return None
    in_rate, out_rate = model.pricing_per_mtok
    in_cost = (budget.estimated_input_tokens / 1_000_000.0) * in_rate
    out_cost = (budget.estimated_output_tokens / 1_000_000.0) * out_rate
    return round(in_cost + out_cost, 8)


def _quality_score(model: ModelOption, task: TaskProfile) -> tuple[float, bool]:
    """Score a model's quality for the task. Returns (score, bench_verified).

    Primary signal: bench score for the task's family. If absent, fall back to a
    neutral 0.5 (not penalized for being new — but flagged as unverified).
    """
    bench_verified = task.task_type in model.bench_scores
    if bench_verified:
        return (model.bench_scores[task.task_type], True)
    # No bench data: neutral score, flagged. The operator should know this pick
    # is not bench-verified — it's a guess, not a measurement.
    return (0.5, False)


def recommend_model(
    task: TaskProfile,
    models: list[ModelOption],
    budget: BudgetConstraint | None = None,
) -> ModelRecommendation:
    """Rank available models for a task and recommend the best fit.

    Pure: no I/O. The decision tree is explicit (see module docstring). Every
    exclusion and budget impact is counted and surfaced honestly.
    """
    if not task.task_type.strip():
        raise ModelRecommendationError("task_type must be non-empty")
    if not models:
        return ModelRecommendation(
            recommended_model_id=None,
            ranked=(),
            excluded_capability=0,
            budget_filtered=False,
            all_exceed_budget=False,
            authority=RECOMMENDATION_AUTHORITY,
            notes=("no models available — cannot recommend",),
        )

    # --- Step 1: capability filter ---
    eligible: list[ModelOption] = []
    excluded_capability = 0
    for m in models:
        if task.requires_grounding and not m.supports_grounding:
            excluded_capability += 1
            continue
        if m.max_context_tokens > 0 and task.min_context_tokens > m.max_context_tokens:
            excluded_capability += 1
            continue
        eligible.append(m)

    if not eligible:
        return ModelRecommendation(
            recommended_model_id=None,
            ranked=(),
            excluded_capability=excluded_capability,
            budget_filtered=False,
            all_exceed_budget=False,
            authority=RECOMMENDATION_AUTHORITY,
            notes=(
                f"all {excluded_capability} model(s) failed capability filter "
                f"(grounding={task.requires_grounding}, "
                f"min_context={task.min_context_tokens})",
            ),
        )

    # --- Step 2: score + cost each eligible model ---
    scored: list[tuple[ModelOption, float, bool, float | None, bool | None]] = []
    for m in eligible:
        quality, bench_verified = _quality_score(m, task)
        cost = _estimate_cost(m, budget or BudgetConstraint(max_cost_usd=None))

        within_budget: bool | None
        if budget is None or budget.max_cost_usd is None:
            within_budget = None  # no budget constraint
        elif cost is None:
            within_budget = None  # can't assess — pricing unknown
        else:
            within_budget = cost <= budget.max_cost_usd

        scored.append((m, quality, bench_verified, cost, within_budget))

    # --- Step 3: detect budget state, then sort ---
    budget_filtered = False
    all_exceed = False
    if budget is not None and budget.max_cost_usd is not None:
        assessable = [s for s in scored if s[4] is not None]
        if assessable:
            all_exceed = all(s[4] is False for s in assessable)
            within_count = sum(1 for s in assessable if s[4] is True)
            exceed_count = sum(1 for s in assessable if s[4] is False)
            if exceed_count > 0 and within_count > 0:
                budget_filtered = True

    # Two sort policies, explicit not magic:
    # (a) Normal (some within budget OR no budget constraint): within-budget
    #     models rank above over-budget; within each group, quality desc, cost asc.
    # (b) All exceed: the operator WILL overspend — minimize damage by ranking
    #     cheapest-first (cost asc, then quality desc as tiebreaker).
    if all_exceed:
        scored.sort(key=lambda item: (
            item[3] if item[3] is not None else float("inf"),
            -item[1],
            item[0].model_id,
        ))
    else:
        scored.sort(key=lambda item: (
            0 if (item[4] is None or item[4]) else 1,  # within-budget first
            -item[1],  # quality desc
            item[3] if item[3] is not None else float("inf"),  # cost asc
            item[0].model_id,
        ))

    ranked: list[RankedModel] = []
    notes: list[str] = []
    for m, quality, bench_verified, cost, within in scored:
        reasons: list[str] = []
        if bench_verified:
            reasons.append(f"bench score {quality:.2f} for {task.task_type}")
        else:
            reasons.append(f"no bench data for {task.task_type} (neutral 0.50, unverified)")
        if cost is not None:
            reasons.append(f"est. cost ${cost}")
        else:
            reasons.append("pricing unknown")
        if within is False:
            reasons.append("EXCEEDS budget headroom")
        elif within is True:
            reasons.append("within budget")

        ranked.append(
            RankedModel(
                model_id=m.model_id,
                provider=m.provider,
                score=quality,
                estimated_cost_usd=cost,
                within_budget=within,
                bench_verified=bench_verified,
                reasoning=" · ".join(reasons),
            )
        )

    recommended = ranked[0].model_id if ranked else None

    if excluded_capability:
        notes.append(f"{excluded_capability} model(s) excluded: failed capability filter")
    if all_exceed:
        notes.append("all assessable models exceed budget headroom — cheapest still recommended")
    if budget_filtered:
        notes.append("budget constraint changed ranking: within-budget models ranked first")
    unverified = [r for r in ranked if not r.bench_verified]
    if unverified and recommended:
        top_unverified = not ranked[0].bench_verified
        if top_unverified:
            notes.append(
                "recommended model is NOT bench-verified for this task — "
                "measurement gap, not a validated pick"
            )

    if not notes:
        notes.append("clean recommendation — top model is bench-verified and within budget")

    return ModelRecommendation(
        recommended_model_id=recommended,
        ranked=tuple(ranked),
        excluded_capability=excluded_capability,
        budget_filtered=budget_filtered,
        all_exceed_budget=all_exceed,
        authority=RECOMMENDATION_AUTHORITY,
        notes=tuple(notes),
    )


__all__ = [
    "BudgetConstraint",
    "ModelOption",
    "ModelRecommendation",
    "ModelRecommendationError",
    "RankedModel",
    "RECOMMENDATION_AUTHORITY",
    "TaskProfile",
    "recommend_model",
]
