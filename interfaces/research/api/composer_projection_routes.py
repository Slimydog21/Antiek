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

from decimal import Decimal
from typing import Annotated, Any, Literal

import yaml
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from interfaces.research.api.settings_budget import (
    BudgetResponse,
    ModelDecisionRequest,
    build_model_decision_candidates,
    read_operator_budget,
)
from runtime.research_runner.cost_projection import project_cascade_cost
from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
)
from substrate.dispatch.advisory_decision import (
    DecisionCandidate,
    rank_model_candidates,
)
from substrate.dispatch.composer_model_projection import (
    BudgetSnapshot,
    ComposerModelProjection,
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

    model_config = ConfigDict(extra="forbid", strict=True)

    unit: UsageUnit
    maximum: int = Field(ge=0, le=10_000_000)


class ChoiceBody(BaseModel):
    """The operator's explicit per-prompt model choice (optional — curated default if absent)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)


class ComposerProjectionRequest(BaseModel):
    """A composer's request for its per-prompt model projection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    task: DecisionTaskName
    bounded_usage: list[BoundedUsageBody] = Field(min_length=1, max_length=5)
    choice: ChoiceBody | None = None
    operation: str = Field(default="deep_research", min_length=1, max_length=64)
    seam_id: str = Field(default="composer", min_length=1, max_length=128)

    @model_validator(mode="after")
    def usage_is_unique_and_matches_decision_bounds(self) -> ComposerProjectionRequest:
        for name, value in (
            ("operation", self.operation),
            ("seam_id", self.seam_id),
        ):
            if value != value.strip():
                raise ValueError(f"{name} must be trimmed")
        if self.choice is not None:
            for name, value in (
                ("choice provider", self.choice.provider),
                ("choice model", self.choice.model),
            ):
                if value != value.strip():
                    raise ValueError(f"{name} must be trimmed")
        units = [usage.unit for usage in self.bounded_usage]
        if len(units) != len(set(units)):
            raise ValueError("bounded usage units must be unique")
        if not any(usage.maximum > 0 for usage in self.bounded_usage):
            raise ValueError("bounded usage must include at least one positive maximum")
        by_unit = {usage.unit: usage.maximum for usage in self.bounded_usage}
        if by_unit.get("input_token", 0) > 2_500_000:
            raise ValueError("input_token maximum exceeds the decision projection contract")
        if by_unit.get("output_token", 0) > 1_000_000:
            raise ValueError("output_token maximum exceeds the decision projection contract")
        return self


def read_composer_projection_budget() -> BudgetResponse:
    """FastAPI dependency for the Settings-owned operator budget snapshot."""
    return read_operator_budget()


def _budget_snapshot(budget: object) -> BudgetSnapshot:
    """Read the operator budget honestly — None when a value is unmeasurable.

    Reuses ``read_operator_budget`` (the Settings source) so the composer bar and the
    Settings bar share one source of truth. ``spent_usd`` is ``None`` when the daemon
    sidecar is absent (honest unknown-spend), never fabricated ``0.0``.
    """
    if type(budget) is not BudgetResponse:
        raise TypeError("budget source returned an invalid value")
    # Rebuild the value so forged/mutated model instances cannot cross this boundary.
    validated = BudgetResponse.model_validate(budget.model_dump())
    snapshot = BudgetSnapshot(
        daily_cap_usd=validated.daily_cap_usd,
        spent_usd=validated.spent_usd,
    )
    if validated.spent_status == "known":
        if (
            validated.daily_cap_usd is None
            or validated.spent_usd is None
            or validated.remaining_usd is None
        ):
            raise ValueError("known budget spend requires cap, spent, and remaining values")
        expected = Decimal(str(validated.daily_cap_usd)) - Decimal(
            str(validated.spent_usd)
        )
        if Decimal(str(validated.remaining_usd)) != expected:
            raise ValueError("budget remaining conflicts with cap and spend")
    elif validated.spent_status == "unknown":
        if validated.spent_usd is not None or validated.remaining_usd is not None:
            raise ValueError("unknown budget spend cannot claim spent or remaining values")
    elif validated.daily_cap_usd is not None or validated.remaining_usd is not None:
        raise ValueError("no-cap budget status cannot claim cap or remaining values")
    return snapshot


def _server_candidates(
    request: Request,
    body: ComposerProjectionRequest,
    budget: BudgetResponse,
) -> tuple[DecisionCandidate, ...]:
    """Resolve candidates from server config/registration/bench state only."""
    usage = {item.unit: item.maximum for item in body.bounded_usage}
    source_candidates = build_model_decision_candidates(
        request,
        ModelDecisionRequest(
            task=body.task,
            input_chars=usage.get("input_token", 0) * 4,
            expected_output_tokens=usage.get("output_token", 0),
        ),
        budget=budget,
    )
    decision = rank_model_candidates(body.task, source_candidates)
    candidates: list[DecisionCandidate] = []
    seen_routes: set[tuple[str, str]] = set()
    for row in decision.ranked:
        candidate = row.candidate
        route = (candidate.provider, candidate.model)
        if route in seen_routes:
            continue
        seen_routes.add(route)
        candidates.append(candidate)
    if not candidates:
        raise ValueError("server model decision returned no candidates")
    return tuple(candidates)


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
    request: Request,
    req: ComposerProjectionRequest,
    budget_readout: Annotated[BudgetResponse, Depends(read_composer_projection_budget)],
) -> dict[str, Any]:
    """Resolve the per-prompt model projection. Advisory — never authorizes."""
    try:
        budget = _budget_snapshot(budget_readout)
        candidates = _server_candidates(request, req, budget_readout)
    except (ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        raise HTTPException(
            status_code=503,
            detail="composer model decision source is unavailable",
        ) from exc
    projector = _make_projector(req)
    choice = (req.choice.provider, req.choice.model) if req.choice is not None else None
    if choice is not None and choice not in {
        (candidate.provider, candidate.model) for candidate in candidates
    }:
        raise HTTPException(status_code=400, detail="chosen model route is unavailable")
    try:
        projection = resolve_composer_projection(
            task=req.task,
            candidates=candidates,
            budget=budget,
            chosen=choice,
            project=projector,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="composer projection could not be resolved",
        ) from exc
    return _serialize(projection)


def _serialize(projection: ComposerModelProjection) -> dict[str, Any]:
    """Serialize a revalidated projection without losing Decimal precision.

    ``chosen_projection.maximum_cost_usd`` is a canonical Decimal string, not
    a JSON number.  This preserves values outside IEEE-754's finite range;
    consumers may use ``reservation_cents`` for an integer-cent display/hold.
    """
    projection.__post_init__()
    chosen_projection = projection.chosen_projection
    chosen_serialized: dict[str, Any] | None = None
    if chosen_projection is not None:
        chosen_serialized = {
            "seam_id": chosen_projection.seam_id,
            "provider": chosen_projection.provider,
            "model": chosen_projection.model,
            "operation": chosen_projection.operation,
            "maximum_cost_usd": str(chosen_projection.maximum_cost_usd),
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
    "read_composer_projection_budget",
    "register_composer_projection_routes",
]
