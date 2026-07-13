"""Composer-facing model projection — per-prompt model choice + live budget readout (asks #8/#10, Slice A).

The operator's vision (goal objective, asks #8/#10): *"there should be a decision tree tab
where the model should be selected (also include a bar of how much usage has been used on that
API key given the limit I set in my budget in settings; also it would be cool to display a
projection of how the proposed prompt would affect that limit)."* This module is the pure
composition seam that makes that per-prompt experience possible.

**What already exists on main (do not rebuild — model-decision-composer spec §1):**

* ``substrate/dispatch/advisory_decision.py`` (#2029): ``rank_model_candidates(task, candidates)``
  → ``DecisionResult`` with ranked candidates, quality basis (measured vs static_prior),
  eligibility, and the advisory ``would_exceed_budget`` hint.
* ``runtime/research_runner/protocol.py``: ``CostProjection`` — the authoritative server-side
  projection (``maximum_cost_usd``, ``disposition``, ``ineligibility``).
* ``interfaces/research/api/settings_budget.py`` (#2029): the Settings budget bar.

**The gap this module closes (spec §2):** none of the above is wired into the prompt composers
at composition time. THIS resolver is the single composition point — it takes the advisory
ranking + the authoritative projection for the chosen candidate + the budget snapshot, and
folds them into one ``ComposerModelProjection`` the composer renders. The API route (Slice B)
and the composer UI (Slices C/D) consume this; neither re-derives.

**Load-bearing invariants (spec §3 — each is a test):**

1. **Client projection is explanatory, NOT authorization.** ``authority="advisory_explanatory"``;
   the server repeats the budget + eligibility check at execution time (byok route-authority
   spec §5). A composer-side "projected OK" never authorizes a call the server would reject.
2. **Unknown pricing is visibly unknown.** ``pricing_status="unknown"`` when the candidate's
   ``estimated_usd_low/high`` are ``None``; the readout shows "unknown," never ``$0.00``.
3. **``would_exceed_budget`` is derived from the authoritative projection, not client rate
   math.** The chosen candidate's over-budget verdict comes from
   ``CostProjection.maximum_cost_usd`` vs ``remaining_usd`` — server-side data, never a stale
   client rate table. ``None`` when either is unmeasurable (never fabricated ``False``).
4. **Quality basis is carried.** A recommendation grounded in ``measured`` (bench samples) is
   distinct from ``static_prior`` — the composer never mistakes a prior for a measurement.
5. **Curated default is the honest fallback.** Absent an explicit choice, ``chosen_*`` are
   ``None`` and a note records "curated default — no explicit user choice projected"; the
   composer uses the existing curated tier. Choosing a model projects ONLY that candidate.
6. **The ranked list is the advisory ranking verbatim** — rank, tier, provider/model, quality
   score + basis, eligibility, pricing status. The decision-tree tab (Slice D) reads this
   directly; nothing is re-ranked or re-derived here.

**Pure — no dispatch, no catalog I/O, no clock.** The projector is an injected
:class:`ProjectionResolver` Protocol; the resolver only composes. Deterministic + immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from runtime.research_runner.protocol import CostProjection
from substrate.dispatch.advisory_decision import (
    DecisionCandidate,
    DecisionResult,
    DecisionTask,
    rank_model_candidates,
)

PricingStatus = Literal["known", "unknown"]
QualityBasis = Literal["measured", "static_prior"]


@runtime_checkable
class ProjectionResolver(Protocol):
    """Resolve the authoritative cost projection for one (provider, model) pair.

    The caller (API route, Slice B) adapts the real ``project_cascade_cost`` to this
    seam; tests inject a fake. Keeping the projector injected is what makes the
    resolver pure (no catalog, no dispatch, no file I/O).
    """

    def __call__(self, provider: str, model: str) -> CostProjection:
        ...


@dataclass(frozen=True)
class BudgetSnapshot:
    """The budget the projection is measured against. ``None`` = unmeasurable.

    ``daily_cap_usd`` None means no cap is set (unbounded); ``spent_usd`` None means
    spend is unknown. Both surface honestly downstream — never coerced to 0.0.
    """

    daily_cap_usd: float | None
    spent_usd: float | None


@dataclass(frozen=True)
class ComposerCandidateView:
    """One ranked candidate as the composer/decision-tree tab renders it."""

    rank: int
    tier: str
    provider: str
    model: str
    quality_score: float
    quality_basis: QualityBasis
    eligible: bool
    pricing_status: PricingStatus
    estimated_usd_low: float | None
    estimated_usd_high: float | None


@dataclass(frozen=True)
class ComposerModelProjection:
    """The single composer-facing projection for one prompt's model decision."""

    task: DecisionTask
    recommended_tier: str | None
    ranked_candidates: tuple[ComposerCandidateView, ...]
    budget: BudgetSnapshot
    remaining_usd: float | None
    chosen_provider: str | None
    chosen_model: str | None
    chosen_projection: CostProjection | None
    would_exceed_budget: bool | None
    pricing_status: PricingStatus
    authority: str
    notes: tuple[str, ...]


def _pricing_status(candidate: DecisionCandidate) -> PricingStatus:
    """Known iff both cost bounds are present; else unknown (never $0.00)."""
    if candidate.estimated_usd_low is None or candidate.estimated_usd_high is None:
        return "unknown"
    return "known"


def _remaining(budget: BudgetSnapshot) -> float | None:
    """Remaining = cap − spent. None when either is unmeasurable."""
    if budget.daily_cap_usd is None or budget.spent_usd is None:
        return None
    return budget.daily_cap_usd - budget.spent_usd


def resolve_composer_projection(
    *,
    task: DecisionTask,
    candidates: tuple[DecisionCandidate, ...],
    budget: BudgetSnapshot,
    chosen: tuple[str, str] | None,
    project: ProjectionResolver,
    ranking: DecisionResult | None = None,
) -> ComposerModelProjection:
    """Compose the advisory ranking + the authoritative projection into one view.

    ``chosen`` is the explicit operator choice as ``(provider, model)``; ``None`` is
    the curated-default fallback (no explicit choice projected). ``project`` resolves
    the authoritative ``CostProjection`` for the chosen candidate only (the ranked
    list carries advisory pricing for the rest). ``ranking`` defaults to
    ``rank_model_candidates(task, candidates)``; injectable for hermetic tests.
    """
    decision: DecisionResult = ranking if ranking is not None else rank_model_candidates(
        task, candidates
    )

    ranked_views: tuple[ComposerCandidateView, ...] = tuple(
        ComposerCandidateView(
            rank=ranked.rank,
            tier=ranked.candidate.tier,
            provider=ranked.candidate.provider,
            model=ranked.candidate.model,
            quality_score=ranked.quality_score,
            quality_basis=ranked.quality_basis,
            eligible=ranked.eligible,
            pricing_status=_pricing_status(ranked.candidate),
            estimated_usd_low=ranked.candidate.estimated_usd_low,
            estimated_usd_high=ranked.candidate.estimated_usd_high,
        )
        for ranked in decision.ranked
    )

    remaining = _remaining(budget)
    notes: list[str] = ["authority=advisory_explanatory — server re-validates at execution"]

    chosen_view: ComposerCandidateView | None = None
    if chosen is not None:
        provider, model = chosen
        chosen_view = next(
            (v for v in ranked_views if v.provider == provider and v.model == model),
            None,
        )

    chosen_projection: CostProjection | None = None
    would_exceed: bool | None = None
    chosen_pricing_status: PricingStatus = "unknown"

    if chosen is None:
        notes.append("curated default — no explicit user choice projected")
    elif chosen_view is None:
        notes.append(
            "explicit choice not in the ranked candidate set — server will validate "
            "the route at execution (byok route-authority)"
        )
        would_exceed = None
    else:
        chosen_pricing_status = chosen_view.pricing_status
        try:
            chosen_projection = project(chosen_view.provider, chosen_view.model)
        except Exception:  # noqa: BLE001 — projector failure is honest-unknown, not a crash
            chosen_projection = None
            notes.append(
                "projection resolver raised — chosen_projection withheld (unknown, not $0.00)"
            )
        would_exceed = _would_exceed(chosen_projection, remaining)
        if would_exceed is True:
            notes.append("would_exceed_budget=true — this prompt would cross the ceiling")
        elif would_exceed is False:
            notes.append("would_exceed_budget=false — within the ceiling (server re-validates)")
        else:
            notes.append("would_exceed_budget=null — budget or projection unmeasurable")

    return ComposerModelProjection(
        task=task,
        recommended_tier=decision.recommended_tier,
        ranked_candidates=ranked_views,
        budget=budget,
        remaining_usd=remaining,
        chosen_provider=chosen_view.provider if chosen_view is not None else None,
        chosen_model=chosen_view.model if chosen_view is not None else None,
        chosen_projection=chosen_projection,
        would_exceed_budget=would_exceed,
        pricing_status=chosen_pricing_status,
        authority="advisory_explanatory",
        notes=tuple(notes),
    )


def _would_exceed(
    projection: CostProjection | None, remaining: float | None
) -> bool | None:
    """Derive the over-budget verdict from the authoritative projection.

    Server-side ``maximum_cost_usd`` vs ``remaining`` — never client rate math.
    ``None`` when either is unmeasurable (never fabricated False).
    """
    if projection is None or remaining is None:
        return None
    return float(projection.maximum_cost_usd) > remaining


__all__ = [
    "BudgetSnapshot",
    "ComposerCandidateView",
    "ComposerModelProjection",
    "PricingStatus",
    "ProjectionResolver",
    "resolve_composer_projection",
]
