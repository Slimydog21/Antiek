"""Composer projection route — exposes ComposerModelProjection over HTTP (asks #8/#10, Slice B).

The model-decision-composer spec §4 Slice B: one ``GET``/``POST`` that resolves the
per-prompt model decision + live budget projection for a draft prompt, served to the
composer UI (Slice C/D). This route is a THIN HTTP adapter over the pure resolver
(``resolve_composer_projection``, #2057 Slice A); it never re-ranks, never re-derives.

**Honesty rules (load-bearing, spec §3):**

* **The client supplies route identity + bounded usage only — never rates.** The server
  catalog supplies rates and capabilities (``CostProjectionRequest`` docstring); a client
  cannot make itself hold-eligible. Bounded usage is the operator's enforced maximum for
  THIS prompt (input/output token caps); rates come from the server.
* **The projection is explanatory, not authorization.** ``authority="advisory_explanatory"``;
  the server re-validates budget + eligibility at execution (byok route-authority §5).
* **Budget is read from the same daemon budget source as Settings** (``DaemonBudget``) so the
  composer bar and the Settings bar never disagree — one source of truth for ``spent_usd`` /
  ``daily_cap_usd``. Unknown spent (no ledger) → ``None`` honestly, never ``0.0``.
* **Value-free errors.** Projection/ranking failures surface a typed message, never a key or
  rate leak. ``extra="forbid"`` on all bodies.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from interfaces.research.api.settings_budget import read_operator_budget
from runtime.research_runner.cost_projection import project_cascade_cost
from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
)
from substrate.dispatch.advisory_decision import DecisionCandidate
from substrate.dispatch.composer_model_projection import (
    BudgetSnapshot,
    ProjectionResolver,
    resolve_composer_projection,
)

composer_projection_router = APIRouter(
    prefix="/settings/composer-projection",
    tags=["composer-model-projection"],
)

_USAGE_UNIT_MAP: dict[str, BillingUnit] = {member.value: member for member in BillingUnit}


def _unit(value: str) -> BillingUnit:
    """Map the API string to the BillingUnit enum (validated by the Literal)."""
    try:
        return _USAGE_UNIT_MAP[value]
    except KeyError as exc:  # pragma: no cover — the Literal body makes this unreachable
        raise ValueError(f"unknown usage unit {value!r}") from exc

UsageUnit = Literal["call", "input_token", "output_token", "http_request", "local_operation"]
DecisionTaskName = Literal[
    "deep_research",
    "research_synthesis",
    "reading",
    "twin_note",
    "writing",
    "multimedia",
    "general",
]


class BoundedUsageBody(BaseModel):
    """The operator's enforced maximum usage for this prompt. Rates are NOT here."""

    model_config = ConfigDict(extra="forbid")

    unit: UsageUnit
    maximum: int = Field(ge=0, le=10_000_000)


class CandidateBody(BaseModel):
    """One candidate the server ranks. Cost estimates are advisory (may be null)."""

    model_config = ConfigDict(extra="forbid")

    tier: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    ready: bool = Field(strict=True)
    estimated_usd_low: float | None = Field(default=None, ge=0.0)
    estimated_usd_high: float | None = Field(default=None, ge=0.0)
    would_exceed_budget: bool | None = None
    benchmark_score: float | None = Field(default=None, ge=0.0, le=1.0)
    benchmark_samples: int | None = Field(default=None, ge=0)


class ChoiceBody(BaseModel):
    """The operator's explicit per-prompt model choice (optional — curated default if absent)."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)


class ComposerProjectionRequest(BaseModel):
    """A composer's request for its per-prompt model projection."""

    model_config = ConfigDict(extra="forbid")

    task: DecisionTaskName
    candidates: list[CandidateBody] = Field(min_length=1)
    bounded_usage: list[BoundedUsageBody] = Field(min_length=1)
    choice: ChoiceBody | None = None
    operation: str = Field(default="deep_research", min_length=1, max_length=64)
    seam_id: str = Field(default="composer", min_length=1, max_length=128)


# Injectable so tests can swap the budget readout (production reads the daemon budget
# sidecar via settings_budget.read_operator_budget — one source of truth shared with the
# Settings page, so the composer bar and the Settings bar never disagree).
_BUDGET_READ: Callable[[], object] | None = None


def set_composer_projection_budget_read(
    read: Callable[[], object] | None,
) -> None:
    """Inject a budget-read callable (tests); None restores the production readout."""
    global _BUDGET_READ
    _BUDGET_READ = read


def _budget_snapshot() -> BudgetSnapshot:
    """Read the operator budget honestly — None when a value is unmeasurable.

    Reuses ``read_operator_budget`` (the Settings source) so the composer bar and the
    Settings bar share one source of truth. ``spent_usd`` is ``None`` when the daemon
    sidecar is absent (honest unknown-spend), never fabricated ``0.0``.
    """
    budget = _BUDGET_READ() if _BUDGET_READ is not None else read_operator_budget()
    cap = getattr(budget, "daily_cap_usd", None)
    spent = getattr(budget, "spent_usd", None)
    return BudgetSnapshot(daily_cap_usd=cap, spent_usd=spent)


def _to_candidate(body: CandidateBody) -> DecisionCandidate:
    return DecisionCandidate(
        tier=body.tier,
        provider=body.provider,
        model=body.model,
        ready=body.ready,
        estimated_usd_low=body.estimated_usd_low,
        estimated_usd_high=body.estimated_usd_high,
        would_exceed_budget=body.would_exceed_budget,
        benchmark_score=body.benchmark_score,
        benchmark_samples=body.benchmark_samples,
    )


def _make_projector(
    request: ComposerProjectionRequest,
) -> ProjectionResolver:
    """Adapt the server cost projector to the resolver's Protocol.

    The client supplies only route identity + bounded usage (never rates); the server
    catalog resolves rates inside ``project_cascade_cost``. A projector failure is caught
    by the resolver (chosen_projection withheld → honest unknown), so it is NOT caught here.
    """

    def resolve(provider: str, model: str) -> CostProjection:
        cp_request = CostProjectionRequest(
            seam_id=request.seam_id,
            provider=provider,
            model=model,
            operation=request.operation,
            bounded_usage=tuple(
                BoundedUsage(unit=_unit(usage.unit), maximum=usage.maximum)
                for usage in request.bounded_usage
            ),
        )
        return project_cascade_cost(cp_request)

    return resolve


@composer_projection_router.post("/resolve")
def resolve_projection(
    req: ComposerProjectionRequest,
) -> dict[str, Any]:
    """Resolve the per-prompt model projection. Advisory — never authorizes."""
    candidates = tuple(_to_candidate(c) for c in req.candidates)
    budget = _budget_snapshot()
    projector = _make_projector(req)
    choice = (req.choice.provider, req.choice.model) if req.choice is not None else None
    try:
        projection = resolve_composer_projection(
            task=req.task,
            candidates=candidates,
            budget=budget,
            chosen=choice,
            project=projector,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(projection)


def _serialize(projection: Any) -> dict[str, Any]:
    """Serialize the projection to JSON. The CostProjection's Decimal fields become floats."""
    chosen_projection = projection.chosen_projection
    chosen_serialized: dict[str, Any] | None = None
    if chosen_projection is not None:
        chosen_serialized = {
            "seam_id": chosen_projection.seam_id,
            "provider": chosen_projection.provider,
            "model": chosen_projection.model,
            "operation": chosen_projection.operation,
            "maximum_cost_usd": float(chosen_projection.maximum_cost_usd),
            "reservation_cents": chosen_projection.reservation_cents,
            "disposition": str(chosen_projection.disposition.value),
            "ineligibility": (
                str(chosen_projection.ineligibility.value)
                if chosen_projection.ineligibility is not None
                else None
            ),
        }
    return {
        "task": projection.task,
        "recommended_tier": projection.recommended_tier,
        "ranked_candidates": [
            {
                "rank": c.rank,
                "tier": c.tier,
                "provider": c.provider,
                "model": c.model,
                "quality_score": c.quality_score,
                "quality_basis": c.quality_basis,
                "eligible": c.eligible,
                "pricing_status": c.pricing_status,
                "estimated_usd_low": c.estimated_usd_low,
                "estimated_usd_high": c.estimated_usd_high,
            }
            for c in projection.ranked_candidates
        ],
        "budget": {
            "daily_cap_usd": projection.budget.daily_cap_usd,
            "spent_usd": projection.budget.spent_usd,
        },
        "remaining_usd": projection.remaining_usd,
        "chosen_provider": projection.chosen_provider,
        "chosen_model": projection.chosen_model,
        "chosen_projection": chosen_serialized,
        "would_exceed_budget": projection.would_exceed_budget,
        "pricing_status": projection.pricing_status,
        "authority": projection.authority,
        "notes": list(projection.notes),
    }


def register_composer_projection_routes(app: FastAPI) -> None:
    app.include_router(composer_projection_router)


__all__ = [
    "composer_projection_router",
    "register_composer_projection_routes",
    "set_composer_projection_budget_read",
]
