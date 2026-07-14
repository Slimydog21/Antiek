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

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from runtime.research_runner.protocol import CostProjection, ProjectionDisposition
from substrate.dispatch.advisory_decision import (
    DecisionCandidate,
    DecisionTask,
    rank_model_candidates,
)

PricingStatus = Literal["known", "unknown"]
QualityBasis = Literal["measured", "static_prior"]

_DECISION_TASKS = frozenset(
    {
        "deep_research",
        "research_synthesis",
        "reading",
        "twin_note",
        "writing",
        "multimedia",
        "general",
    }
)
_MAX_CANDIDATES = 256
_MAX_IDENTITY_CHARS = 256
_MAX_TIER_CHARS = 64
_MAX_BUDGET_USD = 1_000_000_000_000.0
_MAX_BENCHMARK_SAMPLES = 1_000_000_000
_PROJECTION_UNAVAILABLE_ERRORS = (LookupError, OSError)


@runtime_checkable
class ProjectionResolver(Protocol):
    """Resolve the authoritative cost projection for one (provider, model) pair.

    The caller (API route, Slice B) adapts the real ``project_cascade_cost`` to this
    seam; tests inject a fake. Keeping the projector injected is what makes the
    resolver pure (no catalog, no dispatch, no file I/O).
    """

    def __call__(self, provider: str, model: str) -> CostProjection: ...


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """The budget the projection is measured against. ``None`` = unmeasurable.

    ``daily_cap_usd`` None means no cap is set (unbounded); ``spent_usd`` None means
    spend is unknown. Both surface honestly downstream — never coerced to 0.0.
    """

    daily_cap_usd: float | None
    spent_usd: float | None

    def __post_init__(self) -> None:
        _optional_money(self.daily_cap_usd, "daily_cap_usd")
        _optional_money(self.spent_usd, "spent_usd")


@dataclass(frozen=True, slots=True)
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

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("candidate rank must be a positive integer")
        _bounded_text(self.tier, "tier", _MAX_TIER_CHARS)
        _bounded_text(self.provider, "provider", _MAX_IDENTITY_CHARS)
        _bounded_text(self.model, "model", _MAX_IDENTITY_CHARS)
        if type(self.quality_score) is not float or not math.isfinite(self.quality_score):
            raise ValueError("quality_score must be a finite float")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between zero and one")
        if self.quality_basis not in {"measured", "static_prior"}:
            raise ValueError("quality_basis is invalid")
        if type(self.eligible) is not bool:
            raise TypeError("eligible must be a bool")
        if self.pricing_status not in {"known", "unknown"}:
            raise ValueError("pricing_status is invalid")
        _validate_price_bounds(self.estimated_usd_low, self.estimated_usd_high)
        expected_status = (
            "known"
            if self.estimated_usd_low is not None and self.estimated_usd_high is not None
            else "unknown"
        )
        if self.pricing_status != expected_status:
            raise ValueError("pricing_status conflicts with candidate price bounds")


@dataclass(frozen=True, slots=True)
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

    def __post_init__(self) -> None:
        if self.task not in _DECISION_TASKS:
            raise ValueError("task is invalid")
        if self.authority != "advisory_explanatory":
            raise ValueError("projection authority must remain advisory_explanatory")
        if type(self.ranked_candidates) is not tuple or not self.ranked_candidates:
            raise ValueError("ranked_candidates must be a non-empty tuple")
        if len(self.ranked_candidates) > _MAX_CANDIDATES:
            raise ValueError("ranked_candidates exceeds the projection contract")
        for candidate in self.ranked_candidates:
            if type(candidate) is not ComposerCandidateView:
                raise TypeError("ranked candidate must be ComposerCandidateView")
            candidate.__post_init__()
        if [candidate.rank for candidate in self.ranked_candidates] != list(
            range(1, len(self.ranked_candidates) + 1)
        ):
            raise ValueError("ranked candidate ranks must be contiguous and ordered")
        if len({(row.provider, row.model) for row in self.ranked_candidates}) != len(
            self.ranked_candidates
        ):
            raise ValueError("ranked candidate identities must be unique")
        if self.recommended_tier is not None:
            _bounded_text(self.recommended_tier, "recommended_tier", _MAX_TIER_CHARS)
            if self.recommended_tier not in {
                row.tier for row in self.ranked_candidates if row.eligible
            }:
                raise ValueError("recommended_tier must identify an eligible ranked candidate")
        if type(self.budget) is not BudgetSnapshot:
            raise TypeError("budget must be BudgetSnapshot")
        self.budget.__post_init__()
        _optional_money(self.remaining_usd, "remaining_usd")
        expected_remaining = _remaining(self.budget)
        if self.remaining_usd != expected_remaining:
            raise ValueError("remaining_usd conflicts with the budget snapshot")
        if (self.chosen_provider is None) != (self.chosen_model is None):
            raise ValueError("chosen provider and model must be present together")
        if self.chosen_provider is not None:
            _bounded_text(self.chosen_provider, "chosen_provider", _MAX_IDENTITY_CHARS)
            assert self.chosen_model is not None
            _bounded_text(self.chosen_model, "chosen_model", _MAX_IDENTITY_CHARS)
        chosen_view = next(
            (
                row
                for row in self.ranked_candidates
                if row.provider == self.chosen_provider and row.model == self.chosen_model
            ),
            None,
        )
        if self.chosen_provider is not None and chosen_view is None:
            raise ValueError("chosen route must identify one ranked candidate")
        if self.chosen_projection is not None:
            _validate_projection(
                self.chosen_projection,
                provider=self.chosen_provider,
                model=self.chosen_model,
            )
        if self.would_exceed_budget is not None and type(self.would_exceed_budget) is not bool:
            raise TypeError("would_exceed_budget must be bool or None")
        if self.pricing_status not in {"known", "unknown"}:
            raise ValueError("pricing_status is invalid")
        expected_pricing = "unknown" if chosen_view is None else chosen_view.pricing_status
        if self.pricing_status != expected_pricing:
            raise ValueError("pricing_status conflicts with the chosen candidate")
        expected_exceeds = _would_exceed(
            self.chosen_projection,
            _remaining_decimal(self.budget),
        )
        if self.would_exceed_budget is not expected_exceeds:
            raise ValueError("would_exceed_budget conflicts with projection and budget")
        if type(self.notes) is not tuple or not self.notes or len(self.notes) > 16:
            raise ValueError("notes must be a non-empty bounded tuple")
        for note in self.notes:
            _bounded_text(note, "note", 512)


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip() or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and at most {maximum} characters")
    return value


def _optional_money(value: object, name: str) -> float | None:
    if value is None:
        return None
    if type(value) is not float:
        raise TypeError(f"{name} must be a float or None")
    if not math.isfinite(value) or value < 0.0 or value > _MAX_BUDGET_USD:
        raise ValueError(f"{name} must be finite and between zero and {_MAX_BUDGET_USD:g}")
    return value


def _validate_price_bounds(low: object, high: object) -> None:
    if (low is None) != (high is None):
        raise ValueError("candidate price bounds must both be present or both be unknown")
    if low is None:
        return
    low_value = _optional_money(low, "estimated_usd_low")
    high_value = _optional_money(high, "estimated_usd_high")
    assert low_value is not None and high_value is not None
    if low_value > high_value:
        raise ValueError("estimated_usd_low cannot exceed estimated_usd_high")


def _validate_candidate(candidate: object) -> DecisionCandidate:
    if type(candidate) is not DecisionCandidate:
        raise TypeError("candidate must be an exact DecisionCandidate")
    _bounded_text(candidate.tier, "tier", _MAX_TIER_CHARS)
    _bounded_text(candidate.provider, "provider", _MAX_IDENTITY_CHARS)
    _bounded_text(candidate.model, "model", _MAX_IDENTITY_CHARS)
    if type(candidate.ready) is not bool:
        raise TypeError("candidate ready must be a bool")
    if (
        candidate.would_exceed_budget is not None
        and type(candidate.would_exceed_budget) is not bool
    ):
        raise TypeError("candidate would_exceed_budget must be bool or None")
    _validate_price_bounds(candidate.estimated_usd_low, candidate.estimated_usd_high)
    benchmark = candidate.benchmark_score
    samples = candidate.benchmark_samples
    if (benchmark is None) != (samples is None):
        raise ValueError("benchmark score and sample count must be present together")
    if benchmark is not None:
        if type(benchmark) is not float or not math.isfinite(benchmark):
            raise ValueError("benchmark_score must be a finite float")
        if not 0.0 <= benchmark <= 1.0:
            raise ValueError("benchmark_score must be between zero and one")
        if (
            isinstance(samples, bool)
            or not isinstance(samples, int)
            or not 1 <= samples <= _MAX_BENCHMARK_SAMPLES
        ):
            raise ValueError("benchmark_samples must be a bounded positive integer")
    return candidate


def _validate_projection(
    projection: object, *, provider: str | None, model: str | None
) -> CostProjection:
    if type(projection) is not CostProjection:
        raise TypeError("projector must return an exact CostProjection")
    try:
        projection.__post_init__()
    except AttributeError as exc:
        raise ValueError("projector returned an incomplete CostProjection") from exc
    if provider is None or model is None:
        raise ValueError("a projection requires an explicit chosen route")
    if projection.provider != provider or projection.model != model:
        raise ValueError("projector returned a projection for a different route")
    return projection


def _pricing_status(candidate: DecisionCandidate) -> PricingStatus:
    """Known iff both cost bounds are present; else unknown (never $0.00)."""
    if candidate.estimated_usd_low is None or candidate.estimated_usd_high is None:
        return "unknown"
    return "known"


def _remaining(budget: BudgetSnapshot) -> float | None:
    """Remaining = max(0, cap − spent). None when either is unmeasurable."""
    remaining = _remaining_decimal(budget)
    if remaining is None:
        return None
    return float(remaining)


def _remaining_decimal(budget: BudgetSnapshot) -> Decimal | None:
    budget.__post_init__()
    if budget.daily_cap_usd is None or budget.spent_usd is None:
        return None
    cap = Decimal(str(budget.daily_cap_usd))
    spent = Decimal(str(budget.spent_usd))
    return max(Decimal(0), cap - spent)


def resolve_composer_projection(
    *,
    task: DecisionTask,
    candidates: tuple[DecisionCandidate, ...],
    budget: BudgetSnapshot,
    chosen: tuple[str, str] | None,
    project: ProjectionResolver,
) -> ComposerModelProjection:
    """Compose the advisory ranking + the authoritative projection into one view.

    ``chosen`` is the explicit operator choice as ``(provider, model)``; ``None`` is
    the curated-default fallback (no explicit choice projected). ``project`` resolves
    the authoritative ``CostProjection`` for the chosen candidate only (the ranked
    list carries advisory pricing for the rest). Ranking is always derived here from
    the exact validated candidate tuple; callers cannot inject a conflicting result.
    """
    if task not in _DECISION_TASKS:
        raise ValueError("task is invalid")
    if type(candidates) is not tuple or not 1 <= len(candidates) <= _MAX_CANDIDATES:
        raise ValueError(f"candidates must be a tuple with 1 to {_MAX_CANDIDATES} entries")
    validated_candidates = tuple(_validate_candidate(candidate) for candidate in candidates)
    identities = [(candidate.provider, candidate.model) for candidate in validated_candidates]
    if len(identities) != len(set(identities)):
        raise ValueError("candidate provider/model identities must be unique")
    if type(budget) is not BudgetSnapshot:
        raise TypeError("budget must be an exact BudgetSnapshot")
    budget.__post_init__()
    if chosen is not None:
        if type(chosen) is not tuple or len(chosen) != 2:
            raise TypeError("chosen must be a provider/model tuple or None")
        _bounded_text(chosen[0], "chosen provider", _MAX_IDENTITY_CHARS)
        _bounded_text(chosen[1], "chosen model", _MAX_IDENTITY_CHARS)
    if not callable(project):
        raise TypeError("project must be callable")

    decision = rank_model_candidates(task, validated_candidates)

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

    remaining_decimal = _remaining_decimal(budget)
    remaining = None if remaining_decimal is None else float(remaining_decimal)
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
            projected = project(chosen_view.provider, chosen_view.model)
        except _PROJECTION_UNAVAILABLE_ERRORS:
            chosen_projection = None
            notes.append(
                "projection source unavailable — chosen_projection withheld (unknown, not $0.00)"
            )
        else:
            chosen_projection = _validate_projection(
                projected,
                provider=chosen_view.provider,
                model=chosen_view.model,
            )
        would_exceed = _would_exceed(chosen_projection, remaining_decimal)
        if chosen_projection is not None and (
            chosen_projection.disposition is ProjectionDisposition.INELIGIBLE
        ):
            notes.append("chosen route is ineligible — projection explains refusal only")
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


def _would_exceed(projection: CostProjection | None, remaining: Decimal | None) -> bool | None:
    """Derive the over-budget verdict from the authoritative projection.

    Server-side ``maximum_cost_usd`` vs ``remaining`` — never client rate math.
    ``None`` when either is unmeasurable (never fabricated False).
    """
    if projection is None or remaining is None:
        return None
    projection = _validate_projection(
        projection,
        provider=projection.provider,
        model=projection.model,
    )
    if projection.disposition is ProjectionDisposition.INELIGIBLE:
        return None
    return bool(projection.maximum_cost_usd > remaining)


__all__ = [
    "BudgetSnapshot",
    "ComposerCandidateView",
    "ComposerModelProjection",
    "PricingStatus",
    "ProjectionResolver",
    "resolve_composer_projection",
]
