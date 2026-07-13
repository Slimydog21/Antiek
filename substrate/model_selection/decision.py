"""Model-selection decision-tree — the pure composition layer (advisory).

Executes ``sprint-briefs/model-selection-decision-tree-integration-spec.md`` into
code. Operator vision (asks #8/#9/#10/#11): *"a decision tree tab where the model
should be selected (also include a bar of how much usage has been used on that
API key given the limit I set in my budget in settings; also it would be cool to
display a projection of how the proposed prompt would affect that limit — I want
to know this just in case a given prompt will go over my budget)."*

Every piece of this surface existed as a pure substrate (recommendation engine
#1839, antiek-bench stack #1828-#1832, per-key usage ledger #1841, budget
projection #1838, model-fit-for-task #1970, BYOK settings). **This module is the
composition that ties them into the one advisory object the decision-tree tab
renders.** It reads advisory outputs and re-emits ONE advisory object; it never
dispatches, commits, or selects for the operator.

**Authority is load-bearing:** ``authority = "advisory"`` always. The pure layer
recommends and gates on cost; the OPERATOR consents and picks. The module never
removes a model the operator could choose — ``would_exceed`` WARNS, it does not
block.

**Import-free of off-main siblings.** The recommendation engine (#1839), budget
projection (#1838), usage ledger (#1841), and model-fit axis (#1970) are NOT on
frozen ``origin/main``. This module consumes them via compatible Protocol shapes
(the route layer adapts 1:1 when they land). Pure-Python: stdlib only.

**The four data sources (caller-provided; the route layer computes them):**

1. ``models`` — the BYOK models available to select (the tree's leaves).
2. ``scores`` — the benchmark score table ``(model, task) -> score in [0,1]``
   (from the antiek-bench stack). The recommendation ranks on this.
3. ``usage`` — per-key actuals ``(used_cents, limit_cents)`` (from the ledger).
4. ``projected_cents`` — the already-computed forward cost of the proposed prompt
   (from the budget projection). ``None`` until a model + token estimate exist.

**Honesty rules (load-bearing — acceptance criteria from the spec):**

* **Budget bar ``ratio`` is ``None`` when ``limit_cents == 0``** (unconfigured —
  defer, NEVER ``0.0``; a zero limit means the operator has not set a budget, not
  "0% used").
* **``would_exceed`` is the only hard gate**, and it is advisory: ``True`` only
  when ``limit_cents > 0`` AND ``used + projected > limit``. When
  ``limit_cents == 0`` there is no configured ceiling to trip, so
  ``would_exceed`` is ``False`` (honest — no phony warning) while the ratio stays
  ``None`` (signals unconfigured). The payload NEVER omits a model.
* **Recommendation is order-preserving:** sorted desc by benchmark score, stable
  for ties (input order preserved). The composition does not re-sort by cost or
  filter out under-performers — the operator sees the full ranked list.
* **``projection`` is ``None`` until a forward cost exists** (``projected_cents``
  is ``None``) — defer, never fabricate a projection from a missing estimate.
* **``fit_feedback`` does not block the current decision** — it informs future
  weights (the ask-#11 recursion); the current recommendation stands on current
  benchmark scores.
* scores must be in ``[0,1]``; out-of-range raises (a recording error). A
  duplicate score for the same ``(model, task)`` raises (ambiguous data).
* negative cents/limit raise (a recording error). ``used`` may exceed ``limit``
  (over-budget is a real state, not an error) — surfaced as ``over_limit``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelEntry:
    """One selectable model (a BYOK config leaf). Pure input."""

    model_id: str
    display_name: str
    provider: str


@dataclass(frozen=True)
class BenchScore:
    """One model's measured benchmark score for one task. Pure input."""

    model_id: str
    task_id: str
    score: float  # in [0, 1]


@dataclass(frozen=True)
class UsageActuals:
    """Per-key usage against the operator-set budget. Pure input."""

    used_cents: int  # actual spend this period, >= 0
    limit_cents: int  # operator-set budget ceiling, >= 0 (0 = unconfigured)


@dataclass(frozen=True)
class ModelFitSummary:
    """A lightweight summary of the model-fit-for-task verdict (#1970).

    Compatible shape — the route layer adapts from the real ``ModelFitReport``.
    Attached as ``fit_feedback`` to inform future weights; never blocks a pick.
    """

    chosen_model: str
    verdict: str  # optimal_fit | near_optimal | suboptimal_fit | unknown


@dataclass(frozen=True)
class ModelRanking:
    """One model's position in the recommendation. Advisory, pure."""

    model_id: str
    display_name: str
    provider: str
    score: float
    rank: int  # 1-based, 1 = best score for this task


@dataclass(frozen=True)
class BudgetBar:
    """The budget bar state. Advisory, pure."""

    used_cents: int
    limit_cents: int
    ratio: float | None  # used/limit; None when limit_cents == 0 (unconfigured)
    over_limit: bool  # True when used > limit (current overage); False when unconfigured


@dataclass(frozen=True)
class PromptProjection:
    """The forward-impact of the proposed prompt on the budget bar. Advisory."""

    projected_cents: int
    post_projection_ratio: float | None  # (used+projected)/limit; None when unconfigured
    would_exceed: bool  # True only when limit>0 AND used+projected > limit


@dataclass(frozen=True)
class ModelSelectionDecision:
    """The advisory payload the decision-tree tab renders. Pure, frozen."""

    task_id: str
    recommendation: tuple[ModelRanking, ...]  # sorted desc by score, ties stable
    unranked_models: tuple[str, ...]  # available models with no measured score
    budget_bar: BudgetBar
    projection: PromptProjection | None  # None until projected_cents provided
    fit_feedback: ModelFitSummary | None  # None until a prior selection is scored
    notes: tuple[str, ...]
    authority: str = "advisory"


class ModelSelectionError(ValueError):
    """A model-selection input violates a load-bearing invariant."""


def compose_selection_decision(
    task_id: str,
    models: Sequence[ModelEntry],
    scores: Sequence[BenchScore],
    usage: UsageActuals,
    projected_cents: int | None = None,
    fit_feedback: ModelFitSummary | None = None,
) -> ModelSelectionDecision:
    """Compose the advisory model-selection decision for one task.

    ``task_id`` is the task the selection serves.
    ``models`` are the selectable BYOK models (the tree's leaves).
    ``scores`` is the benchmark table (any tasks; filtered to ``task_id``).
    ``usage`` is the per-key actuals against the budget.
    ``projected_cents`` is the already-computed forward cost (None until a model
    + token estimate exist).
    ``fit_feedback`` is an optional prior-selection verdict (never blocks).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not task_id.strip():
        raise ModelSelectionError("task_id must be non-empty")

    # Validate models + detect duplicate model_id (ambiguous tree).
    seen_model_ids: set[str] = set()
    for model in models:
        if not model.model_id.strip():
            raise ModelSelectionError(f"model_id must be non-empty, got {model.model_id!r}")
        if model.model_id in seen_model_ids:
            raise ModelSelectionError(f"duplicate model_id {model.model_id!r}")
        seen_model_ids.add(model.model_id)

    # Validate scores (range + duplicate (model,task)).
    score_by_model: dict[str, float] = {}
    for row in scores:
        if not row.model_id.strip():
            raise ModelSelectionError(f"model_id must be non-empty, got {row.model_id!r}")
        if not row.task_id.strip():
            raise ModelSelectionError(f"task_id must be non-empty, got {row.task_id!r}")
        if not 0.0 <= row.score <= 1.0:
            raise ModelSelectionError(
                f"score for {row.model_id!r}/{row.task_id!r} must be in [0,1], "
                f"got {row.score!r}"
            )
        if row.task_id != task_id:
            continue  # other tasks ignored
        if row.model_id in score_by_model:
            raise ModelSelectionError(
                f"duplicate score for model {row.model_id!r} on task {task_id!r}"
            )
        score_by_model[row.model_id] = row.score

    # Validate usage (non-negative; used may exceed limit — over-budget is real).
    if usage.used_cents < 0:
        raise ModelSelectionError(f"used_cents must be >= 0, got {usage.used_cents!r}")
    if usage.limit_cents < 0:
        raise ModelSelectionError(f"limit_cents must be >= 0, got {usage.limit_cents!r}")

    # Validate projected_cents (non-negative; caller-computed forward cost).
    if projected_cents is not None and projected_cents < 0:
        raise ModelSelectionError(f"projected_cents must be >= 0, got {projected_cents!r}")

    # --- recommendation: rank available models by benchmark score (desc, stable) ---
    ranked: list[tuple[ModelEntry, float]] = []
    unranked: list[str] = []
    for model in models:  # preserve input order for tie stability
        if model.model_id in score_by_model:
            ranked.append((model, score_by_model[model.model_id]))
        else:
            unranked.append(model.model_id)
    ranked.sort(key=lambda pair: pair[1], reverse=True)  # stable sort: ties keep input order

    recommendation = tuple(
        ModelRanking(
            model_id=model.model_id,
            display_name=model.display_name,
            provider=model.provider,
            score=score,
            rank=position,
        )
        for position, (model, score) in enumerate(ranked, start=1)
    )

    # --- budget bar ---
    budget_bar = _budget_bar(usage)

    # --- projection (None until a forward cost exists) ---
    projection: PromptProjection | None = None
    if projected_cents is not None:
        projection = _projection(usage, projected_cents)

    notes: list[str] = [
        "model-selection decision-tree composition: ranks models by benchmark "
        "score (desc, stable ties), builds the budget bar, composes the forward "
        "projection, and attaches optional fit feedback — into ONE advisory object",
        "authority is advisory always: the pure layer recommends + gates on cost; "
        "the OPERATOR consents and picks; would_exceed WARNS, never blocks — the "
        "payload never omits a model the operator could choose",
        "budget_bar.ratio is None when limit_cents==0 (unconfigured — defer, never "
        "0.0); would_exceed is True only when limit>0 AND used+projected>limit "
        "(no configured ceiling -> no phony warning)",
        "recommendation is order-preserving (sort desc by score, ties stable in "
        "input order); unranked_models are available models with no measured "
        "benchmark score for this task",
        "projection is None until projected_cents is provided (defer, never "
        "fabricate); fit_feedback never blocks the current decision (informs "
        "future weights via the ask-#11 recursion)",
    ]

    return ModelSelectionDecision(
        task_id=task_id,
        recommendation=recommendation,
        unranked_models=tuple(unranked),
        budget_bar=budget_bar,
        projection=projection,
        fit_feedback=fit_feedback,
        notes=tuple(notes),
    )


def _budget_bar(usage: UsageActuals) -> BudgetBar:
    if usage.limit_cents == 0:
        # Unconfigured budget — defer the ratio (never 0.0); no over-limit claim.
        return BudgetBar(
            used_cents=usage.used_cents,
            limit_cents=0,
            ratio=None,
            over_limit=False,
        )
    ratio = usage.used_cents / usage.limit_cents
    return BudgetBar(
        used_cents=usage.used_cents,
        limit_cents=usage.limit_cents,
        ratio=ratio,
        over_limit=usage.used_cents > usage.limit_cents,
    )


def _projection(usage: UsageActuals, projected_cents: int) -> PromptProjection:
    if usage.limit_cents == 0:
        # No configured ceiling -> cannot exceed it (no phony warning); ratio None.
        return PromptProjection(
            projected_cents=projected_cents,
            post_projection_ratio=None,
            would_exceed=False,
        )
    post = usage.used_cents + projected_cents
    return PromptProjection(
        projected_cents=projected_cents,
        post_projection_ratio=post / usage.limit_cents,
        would_exceed=post > usage.limit_cents,
    )
