"""Operator Settings — model inventory + budget readout + prompt cost projection.

SPR-01 (C288): honest Settings substrate for the operator's model-choice and
budget-awareness needs. The adjacent admin router securely registers BYOK
providers but does not grant route authority or route via NotDiamond.

Honesty rules (load-bearing):
  * Spent is ``null`` when no ledger is wired — never invent ``$0 spent``.
  * Cost projection uses ``substrate/dispatch/config.yaml`` tier pricing; when
    rates are ``0.0`` (operator-placeholder), the estimate is ``null`` with an
    explicit note rather than a fake number.
  * Provider list is the live registered set (same source as ``/health``).
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from orchestration.continuous.budget import (
    _ENV_DAILY_CAP,
    DEFAULT_DAILY_CAP_USD,
    DaemonBudget,
    _budget_path,
)
from runtime.research_runner.provider_route_authority import RouteExecutionStatus
from substrate.dispatch.advisory_decision import (
    DecisionCandidate,
    DecisionTask,
    rank_model_candidates,
)
from substrate.research_spend import (
    FallbackHistoryCursor,
    LedgerIntegrityError,
    ResearchSpendLedger,
    default_research_spend_db_path,
)

settings_router = APIRouter(prefix="/settings", tags=["settings"])

SpentStatus = Literal["known", "unknown", "no_cap"]
BenchmarkStatus = Literal["measured", "unavailable"]
_BENCHMARK_REPORT_ENV = "ANTIEK_BENCH_REPORT_PATH"
_MAX_BENCHMARK_REPORT_BYTES = 2 * 1024 * 1024
_MAX_BENCHMARK_AGE = timedelta(days=8)
_MAX_BENCHMARK_FUTURE_SKEW = timedelta(minutes=5)
_TEXT_DECISION_TIERS = frozenset({"flash", "pro", "synthesis", "verify"})
_MAX_FALLBACK_DEPTH = 16


class ModelRow(BaseModel):
    provider_id: str
    registered: bool
    ready: bool
    tier_bindings: list[str] = Field(default_factory=list)
    primary_model: str | None = None
    model_id: str | None = None
    route_eligible: bool = False
    pricing_status: Literal["known", "unknown"] = "unknown"
    hard_ceiling_eligible: bool = False
    execution_status: RouteExecutionStatus = RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
    rate_snapshot: str | None = None
    notes: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelRow]
    count: int
    providers_ready: bool
    source: str = "app.state.registered_providers + dispatch/config.yaml"


class BudgetResponse(BaseModel):
    daily_cap_usd: float | None = Field(ge=0, allow_inf_nan=False)
    spent_usd: float | None = Field(ge=0, allow_inf_nan=False)
    remaining_usd: float | None = Field(ge=0, allow_inf_nan=False)
    spent_status: SpentStatus
    cap_env: str | None
    notes: list[str] = Field(default_factory=list)


class PromptCostEstimateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    tier: str | None = Field(
        default="pro",
        description="Dispatch tier name used when model/provider omitted.",
    )
    input_chars: int = Field(ge=0, default=0)
    expected_output_tokens: int = Field(ge=0, default=500)


class PromptCostEstimateResponse(BaseModel):
    estimated_usd_low: float | None
    estimated_usd_high: float | None
    would_exceed_budget: bool | None
    pricing_known: bool
    notes: list[str] = Field(default_factory=list)
    assumed_input_tokens: int
    assumed_output_tokens: int
    tier: str | None = None
    provider: str | None = None
    model: str | None = None


class FallbackReceiptRouteResponse(BaseModel):
    fallback_index: int = Field(ge=0, le=15)
    provider: str
    model: str
    seam_id: str
    operation: str
    projected_max_cents: int = Field(ge=1)
    state: Literal[
        "unattempted",
        "reserved_not_sent",
        "dispatch_possible",
        "unknown",
        "released",
        "settled",
    ]
    actual_cents: int | None = Field(default=None, ge=0)
    resolved_at: str | None = None
    settlement_evidence_sha256: str | None = None
    settlement_intent_sha256: str | None = None


class FallbackReceiptChainResponse(BaseModel):
    chain_id: str
    manifest_sha256: str
    outcome: Literal["unattempted", "in_progress", "ambiguous", "settled", "exhausted"]
    routes: list[FallbackReceiptRouteResponse] = Field(min_length=1, max_length=16)
    created_at: str


class FallbackReceiptHistoryResponse(BaseModel):
    authority: Literal["read_only_fallback_receipt_history"] = (
        "read_only_fallback_receipt_history"
    )
    items: list[FallbackReceiptChainResponse] = Field(max_length=50)
    next_cursor: str | None = None


class BenchmarkMeasurement(BaseModel):
    task: DecisionTask
    tier: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    samples: int = Field(ge=1, le=1_000_000)


class BenchmarkReport(BaseModel):
    schema_version: Literal["antiek.model-bench.v1"]
    generated_at: datetime
    measurements: list[BenchmarkMeasurement] = Field(max_length=10_000)

    @model_validator(mode="after")
    def measurements_are_unique(self) -> BenchmarkReport:
        keys = [(row.task, row.tier, row.provider, row.model) for row in self.measurements]
        if len(keys) != len(set(keys)):
            raise ValueError("benchmark measurements must be unique by task and route")
        if self.generated_at.tzinfo is None:
            raise ValueError("benchmark generated_at must include a timezone")
        return self


class ModelDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: DecisionTask = "general"
    input_chars: int = Field(default=0, ge=0, le=10_000_000)
    expected_output_tokens: int = Field(default=500, ge=0, le=1_000_000)


class ModelDecisionCandidateResponse(BaseModel):
    rank: int
    tier: str
    provider: str
    model: str
    ready: bool
    eligible: bool
    quality_score: float
    quality_basis: Literal["measured", "static_prior"]
    benchmark_samples: int | None
    estimated_usd_low: float | None
    estimated_usd_high: float | None
    would_exceed_budget: bool | None


class ModelDecisionResponse(BaseModel):
    authority: Literal["advisory"] = "advisory"
    task: DecisionTask
    recommended_tier: str | None
    benchmark_status: BenchmarkStatus
    benchmark_generated_at: str | None
    candidates: list[ModelDecisionCandidateResponse]
    notes: list[str] = Field(default_factory=list)


def _dispatch_config_path() -> Path:
    # interfaces/research/api → repo root
    return Path(__file__).resolve().parents[3] / "substrate" / "dispatch" / "config.yaml"


def _load_dispatch_config() -> dict[str, Any]:
    path = _dispatch_config_path()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _tier_bindings(cfg: dict[str, Any]) -> dict[str, list[str]]:
    """provider_id → tiers where it is reachable as primary or fallback."""
    out: dict[str, list[str]] = {}
    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict):
        return out
    for tier_name, body in tiers.items():
        if not isinstance(body, dict):
            continue
        current: dict[str, Any] | None = body
        seen: set[int] = set()
        depth = 0
        while current is not None and depth < _MAX_FALLBACK_DEPTH:
            identity = id(current)
            if identity in seen:
                break
            seen.add(identity)
            provider = current.get("provider")
            if isinstance(provider, str) and provider:
                names = out.setdefault(provider, [])
                if str(tier_name) not in names:
                    names.append(str(tier_name))
            fallback = current.get("fallback")
            current = fallback if isinstance(fallback, dict) else None
            depth += 1
    return out


def route_ready_provider_ids(registered: set[str]) -> set[str]:
    """Registered providers reachable through a configured dispatch tier."""
    bindings = _tier_bindings(_load_dispatch_config())
    return registered.intersection(bindings)


def _primary_model_for_provider(cfg: dict[str, Any], provider_id: str) -> str | None:
    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict):
        return None
    for body in tiers.values():
        if isinstance(body, dict) and body.get("provider") == provider_id:
            model = body.get("model")
            return str(model) if model is not None else None
    return None


def _resolve_tier_pricing(
    cfg: dict[str, Any],
    *,
    tier: str | None,
    provider: str | None,
    model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None, str | None, list[str]]:
    """Return (pricing_dict, tier, provider, model, notes)."""
    notes: list[str] = []
    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict) or not tiers:
        return None, tier, provider, model, ["dispatch config has no tiers"]

    chosen_tier = tier if tier and tier in tiers else None
    body: dict[str, Any] | None = None

    if chosen_tier is not None:
        raw = tiers[chosen_tier]
        body = raw if isinstance(raw, dict) else None
        if body is not None and (provider or model):
            body = next(
                (
                    route
                    for route in _tier_route_chain(body)
                    if (not provider or route.get("provider") == provider)
                    and (not model or route.get("model") == model)
                ),
                None,
            )
            if body is None:
                notes.append("no route in tier matches requested provider/model")
                return None, chosen_tier, provider, model, notes
    elif provider or model:
        for name, raw in tiers.items():
            if not isinstance(raw, dict):
                continue
            if provider and raw.get("provider") != provider:
                continue
            if model and raw.get("model") != model:
                continue
            chosen_tier = str(name)
            body = raw
            break
        if body is None:
            notes.append("no tier matches requested provider/model")
            return None, tier, provider, model, notes
    else:
        chosen_tier = "pro" if "pro" in tiers else next(iter(tiers))
        raw = tiers[chosen_tier]
        body = raw if isinstance(raw, dict) else None
        notes.append(f"defaulted to tier {chosen_tier!r}")

    if body is None:
        return None, chosen_tier, provider, model, notes + ["tier body missing"]

    resolved_provider = str(body.get("provider") or provider or "")
    resolved_model = str(body.get("model") or model or "")
    pricing = body.get("pricing") if isinstance(body.get("pricing"), dict) else None
    return pricing, chosen_tier, resolved_provider or None, resolved_model or None, notes


def _chars_to_tokens(chars: int) -> int:
    # Conservative ~4 chars/token heuristic; projection, not billing.
    return max(0, (chars + 3) // 4)


def estimate_prompt_cost(
    req: PromptCostEstimateRequest,
    *,
    budget: BudgetResponse | None = None,
) -> PromptCostEstimateResponse:
    cfg = _load_dispatch_config()
    pricing, tier, provider, model, notes = _resolve_tier_pricing(
        cfg,
        tier=req.tier,
        provider=req.provider,
        model=req.model,
    )
    in_tok = _chars_to_tokens(req.input_chars)
    out_tok = req.expected_output_tokens

    if pricing is None:
        return PromptCostEstimateResponse(
            estimated_usd_low=None,
            estimated_usd_high=None,
            would_exceed_budget=None,
            pricing_known=False,
            notes=notes or ["pricing unavailable"],
            assumed_input_tokens=in_tok,
            assumed_output_tokens=out_tok,
            tier=tier,
            provider=provider,
            model=model,
        )

    in_rate = float(pricing.get("input_per_mtok") or 0.0)
    out_rate = float(pricing.get("output_per_mtok") or 0.0)
    if in_rate <= 0.0 and out_rate <= 0.0:
        return PromptCostEstimateResponse(
            estimated_usd_low=None,
            estimated_usd_high=None,
            would_exceed_budget=None,
            pricing_known=False,
            notes=notes
            + [
                "tier pricing is 0.0 placeholder in dispatch/config.yaml — "
                "operator must verify rates before projection is numeric"
            ],
            assumed_input_tokens=in_tok,
            assumed_output_tokens=out_tok,
            tier=tier,
            provider=provider,
            model=model,
        )

    base = (in_tok / 1_000_000.0) * in_rate + (out_tok / 1_000_000.0) * out_rate
    # Low/high band: ±20% heuristic for projection UI, not a guarantee.
    low = round(base * 0.8, 8)
    high = round(base * 1.2, 8)

    would_exceed: bool | None = None
    if budget is not None and budget.remaining_usd is not None:
        would_exceed = high > budget.remaining_usd
    elif budget is not None and budget.spent_status == "unknown":
        notes = notes + ["remaining budget unknown — cannot assert would_exceed"]
        would_exceed = None

    return PromptCostEstimateResponse(
        estimated_usd_low=low,
        estimated_usd_high=high,
        would_exceed_budget=would_exceed,
        pricing_known=True,
        notes=notes,
        assumed_input_tokens=in_tok,
        assumed_output_tokens=out_tok,
        tier=tier,
        provider=provider,
        model=model,
    )


def read_operator_budget() -> BudgetResponse:
    """Read daily cap + spent with honest unknown-spend semantics."""
    notes: list[str] = []
    cap_env: str | None = None
    daily_cap: float | None = None

    for env_name in ("ANTIEK_OPERATOR_BUDGET_USD", _ENV_DAILY_CAP):
        raw = os.environ.get(env_name)
        if raw is None or raw.strip() == "":
            continue
        try:
            parsed_cap = float(raw)
            if not math.isfinite(parsed_cap) or parsed_cap < 0:
                notes.append(f"{env_name} must be finite and non-negative; ignored")
                continue
            daily_cap = parsed_cap
            cap_env = env_name
            break
        except ValueError:
            notes.append(f"{env_name} is not a float; ignored")

    if daily_cap is None:
        # Surface the daemon default as informational only when env unset.
        daily_cap = DEFAULT_DAILY_CAP_USD
        cap_env = None
        notes.append(
            f"no ANTIEK_OPERATOR_BUDGET_USD / {_ENV_DAILY_CAP}; "
            f"showing daemon default cap ${DEFAULT_DAILY_CAP_USD:.2f}/day as reference"
        )

    # Prefer daemon budget sidecar when present (shared daily spend signal).
    # Crucial honesty detail: DaemonBudget.remaining_today() fabricates an
    # in-memory zero-spend snapshot when the file is absent. Settings is a
    # readout, not the daemon, so absence of the sidecar means unknown spend.
    spent: float | None = None
    remaining: float | None = None
    spent_status: SpentStatus = "unknown"
    try:
        if _budget_path().is_file():
            bdg = DaemonBudget(daily_cap_usd=float(daily_cap))
            remaining = float(bdg.remaining_today())
            spent = max(0.0, float(daily_cap) - remaining)
            spent_status = "known"
            notes.append("spent sourced from continuous-daemon daily budget sidecar")
        else:
            notes.append("spent ledger unavailable: daemon sidecar missing")
    except Exception as exc:  # noqa: BLE001 — honesty over crash
        spent = None
        remaining = None
        spent_status = "unknown"
        notes.append(f"spent ledger unavailable: {type(exc).__name__}")

    return BudgetResponse(
        daily_cap_usd=daily_cap,
        spent_usd=spent,
        remaining_usd=remaining,
        spent_status=spent_status,
        cap_env=cap_env,
        notes=notes,
    )


def _read_benchmark_report(
    *, now: datetime | None = None,
) -> tuple[BenchmarkReport | None, list[str]]:
    raw_path = os.environ.get(_BENCHMARK_REPORT_ENV, "").strip()
    if not raw_path:
        return None, ["Antiek-bench report is not configured; quality uses labeled static priors"]
    path = Path(raw_path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        return None, ["Antiek-bench report is unavailable or not a regular absolute file"]
    try:
        if path.stat().st_size > _MAX_BENCHMARK_REPORT_BYTES:
            return None, ["Antiek-bench report exceeds its byte ceiling"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = BenchmarkReport.model_validate(payload)
        observed_at = now or datetime.now(UTC)
        generated_at = report.generated_at.astimezone(UTC)
        if generated_at > observed_at + _MAX_BENCHMARK_FUTURE_SKEW:
            return None, ["Antiek-bench report is future-dated; measured scores were ignored"]
        if observed_at - generated_at > _MAX_BENCHMARK_AGE:
            return None, ["Antiek-bench report is stale; measured scores were ignored"]
        return report, []
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None, ["Antiek-bench report failed validation; measured scores were ignored"]


def _registered_provider_ids(request: Request) -> set[str]:
    raw = getattr(request.app.state, "registered_providers", None)
    if not isinstance(raw, (set, list, tuple, frozenset)):
        return set()
    return {str(provider) for provider in raw}


def _tier_route_chain(tier: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return a bounded, cycle-safe inline fallback chain."""
    routes: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: dict[str, Any] | None = tier
    while current is not None and len(routes) < _MAX_FALLBACK_DEPTH:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        routes.append(current)
        fallback = current.get("fallback")
        current = fallback if isinstance(fallback, dict) else None
    return tuple(routes)


def configured_tier_fallback_routes(tier_name: str) -> tuple[tuple[str, str], ...]:
    """Return one strict server-owned tier chain for operator projection.

    Dispatch's legacy readers tolerate malformed configuration to preserve
    ordinary startup. A hard-ceiling preview must instead reject cycles,
    truncation, duplicate routes, and partial identities as one failed plan.
    """
    if (
        type(tier_name) is not str
        or not tier_name
        or tier_name != tier_name.strip()
        or len(tier_name) > 64
    ):
        raise ValueError("tier name is invalid")
    tiers = _load_dispatch_config().get("tiers")
    if not isinstance(tiers, dict):
        raise ValueError("dispatch tiers are unavailable")
    current = tiers.get(tier_name)
    if not isinstance(current, dict):
        raise ValueError("configured tier is unavailable")
    routes: list[tuple[str, str]] = []
    seen_objects: set[int] = set()
    while True:
        if id(current) in seen_objects:
            raise ValueError("configured fallback chain is cyclic")
        seen_objects.add(id(current))
        if len(routes) >= _MAX_FALLBACK_DEPTH:
            raise ValueError("configured fallback chain exceeds its depth ceiling")
        provider = current.get("provider")
        model = current.get("model")
        if (
            type(provider) is not str
            or not provider
            or provider != provider.strip()
            or len(provider) > 256
            or type(model) is not str
            or not model
            or model != model.strip()
            or len(model) > 256
        ):
            raise ValueError("configured fallback route identity is invalid")
        route = (provider, model)
        if route in routes:
            raise ValueError("configured fallback routes must be unique")
        routes.append(route)
        fallback = current.get("fallback")
        if fallback is None:
            return tuple(routes)
        if not isinstance(fallback, dict):
            raise ValueError("configured fallback route must be an object")
        current = fallback


def _effective_tier_route(
    tier: dict[str, Any],
    ready_ids: set[str],
) -> tuple[str | None, str | None, bool]:
    """Return the first dispatchable route in a tier's inline fallback chain."""
    primary: tuple[str | None, str | None] = (None, None)
    for route_body in _tier_route_chain(tier):
        provider = route_body.get("provider")
        model = route_body.get("model")
        route = (
            provider if isinstance(provider, str) and provider else None,
            model if isinstance(model, str) and model else None,
        )
        if primary == (None, None):
            primary = route
        if route[0] in ready_ids and route[1] is not None:
            return route[0], route[1], True
    return primary[0], primary[1], False


def _model_decision_inputs(
    request: Request,
    req: ModelDecisionRequest,
    *,
    budget: BudgetResponse | None = None,
) -> tuple[
    tuple[DecisionCandidate, ...],
    BudgetResponse,
    BenchmarkReport | None,
    list[str],
]:
    """Return the raw server-owned candidates and their shared context."""
    cfg = _load_dispatch_config()
    tiers = cfg.get("tiers")
    if not isinstance(tiers, dict):
        tiers = {}
    ready_ids = _registered_provider_ids(request)
    resolved_budget = budget if budget is not None else read_operator_budget()
    report, notes = _read_benchmark_report()
    measured: dict[tuple[DecisionTask, str, str, str], BenchmarkMeasurement] = {}
    if report is not None:
        measured = {
            (row.task, row.tier, row.provider, row.model): row
            for row in report.measurements
        }

    candidates: list[DecisionCandidate] = []
    for tier_name in sorted(_TEXT_DECISION_TIERS):
        raw_tier = tiers.get(tier_name)
        if not isinstance(raw_tier, dict):
            continue
        provider, model, ready = _effective_tier_route(raw_tier, ready_ids)
        if provider is None or model is None:
            continue
        projection = estimate_prompt_cost(
            PromptCostEstimateRequest(
                tier=tier_name,
                provider=provider,
                model=model,
                input_chars=req.input_chars,
                expected_output_tokens=req.expected_output_tokens,
            ),
            budget=resolved_budget,
        )
        measurement = measured.get((req.task, tier_name, provider, model))
        candidates.append(
            DecisionCandidate(
                tier=tier_name,
                provider=provider,
                model=model,
                ready=ready,
                estimated_usd_low=projection.estimated_usd_low,
                estimated_usd_high=projection.estimated_usd_high,
                would_exceed_budget=projection.would_exceed_budget,
                benchmark_score=None if measurement is None else measurement.score,
                benchmark_samples=None if measurement is None else measurement.samples,
            )
        )

    return tuple(candidates), resolved_budget, report, notes


def build_model_decision_candidates(
    request: Request,
    req: ModelDecisionRequest,
    *,
    budget: BudgetResponse | None = None,
) -> tuple[DecisionCandidate, ...]:
    """Build unranked candidates from config, provider, budget, and bench state.

    This is the server-owned input seam for adapters that compose the model
    decision with another view.  Scores are raw benchmark measurements here;
    callers must pass them through ``rank_model_candidates`` exactly once.
    """
    candidates, _, _, _ = _model_decision_inputs(request, req, budget=budget)
    return candidates


def build_model_decision(
    request: Request,
    req: ModelDecisionRequest,
    *,
    budget: BudgetResponse | None = None,
) -> ModelDecisionResponse:
    """Build one advisory decision from server-owned state only.

    ``budget`` lets another server adapter compose this decision with an
    authoritative projection from the exact same snapshot.  Ordinary callers
    omit it and retain the Settings endpoint's existing read behavior.
    """
    candidates, resolved_budget, report, notes = _model_decision_inputs(
        request,
        req,
        budget=budget,
    )
    result = rank_model_candidates(req.task, candidates)
    used_measurement = any(row.quality_basis == "measured" for row in result.ranked)
    if report is not None and not used_measurement:
        notes.append("Antiek-bench has no matching measurement for this task and route set")
    if not any(candidate.ready for candidate in candidates):
        notes.append("No text-model provider is registered at boot; no tier is eligible")
    if resolved_budget.remaining_usd is None:
        notes.append("Remaining budget is unknown; budget eligibility is not asserted")
    return ModelDecisionResponse(
        task=req.task,
        recommended_tier=result.recommended_tier,
        benchmark_status="measured" if used_measurement else "unavailable",
        benchmark_generated_at=(
            report.generated_at.isoformat() if report is not None and used_measurement else None
        ),
        candidates=[
            ModelDecisionCandidateResponse(
                rank=row.rank,
                tier=row.candidate.tier,
                provider=row.candidate.provider,
                model=row.candidate.model,
                ready=row.candidate.ready,
                eligible=row.eligible,
                quality_score=row.quality_score,
                quality_basis=row.quality_basis,
                benchmark_samples=row.candidate.benchmark_samples,
                estimated_usd_low=row.candidate.estimated_usd_low,
                estimated_usd_high=row.candidate.estimated_usd_high,
                would_exceed_budget=row.candidate.would_exceed_budget,
            )
            for row in result.ranked
        ],
        notes=notes,
    )


@settings_router.get("/models", response_model=ModelsResponse)
def get_settings_models(request: Request) -> ModelsResponse:
    from .settings_models_admin import user_model_authority_snapshot

    raw_providers = getattr(request.app.state, "registered_providers", None)
    if isinstance(raw_providers, (set, list, tuple, frozenset)):
        registered_set: set[str] = {str(p) for p in raw_providers}
    else:
        registered_set = set()
    cfg = _load_dispatch_config()
    bindings = _tier_bindings(cfg)
    user_authority = user_model_authority_snapshot(request.app)

    # Union of registered + config-known providers so Settings can show
    # configured-but-not-ready rows honestly.
    all_ids = sorted(registered_set | set(bindings.keys()) | set(user_authority.keys()))
    rows: list[ModelRow] = []
    for pid in all_ids:
        provider_registered = pid in registered_set
        provider_bindings = sorted(bindings.get(pid, []))
        # "ready" means reachable through an active dispatch tier, not merely
        # present in the low-level registry. User-added providers intentionally
        # remain unbound until a model-selection vertical grants explicit route
        # authority; reporting them ready here would be product theater.
        is_ready = provider_registered and bool(provider_bindings)
        if is_ready:
            notes = None
        elif provider_registered:
            notes = "registered, but not bound to an active dispatch tier"
        else:
            notes = "configured in dispatch config but not registered at boot"
        rows.append(
            ModelRow(
                provider_id=pid,
                registered=provider_registered,
                ready=is_ready,
                tier_bindings=provider_bindings,
                primary_model=_primary_model_for_provider(cfg, pid),
                model_id=(
                    user_authority[pid].model_id
                    if pid in user_authority
                    else _primary_model_for_provider(cfg, pid)
                ),
                route_eligible=(
                    user_authority[pid].route_eligible if pid in user_authority else is_ready
                ),
                pricing_status=(
                    user_authority[pid].pricing_status if pid in user_authority else "unknown"
                ),
                hard_ceiling_eligible=(
                    user_authority[pid].hard_ceiling_eligible
                    if pid in user_authority
                    else False
                ),
                execution_status=(
                    user_authority[pid].execution_status
                    if pid in user_authority
                    else RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
                ),
                rate_snapshot=(
                    user_authority[pid].rate_snapshot if pid in user_authority else None
                ),
                notes=notes,
            )
        )
    return ModelsResponse(
        models=rows,
        count=len(rows),
        providers_ready=any(row.ready for row in rows),
    )


@settings_router.get("/budget", response_model=BudgetResponse)
def get_settings_budget() -> BudgetResponse:
    return read_operator_budget()


@settings_router.post("/prompt-cost-estimate", response_model=PromptCostEstimateResponse)
def post_prompt_cost_estimate(req: PromptCostEstimateRequest) -> PromptCostEstimateResponse:
    budget = read_operator_budget()
    return estimate_prompt_cost(req, budget=budget)


@settings_router.post("/model-decision", response_model=ModelDecisionResponse)
def post_model_decision(request: Request, req: ModelDecisionRequest) -> ModelDecisionResponse:
    return build_model_decision(request, req)


def _history_cursor(value: str | None) -> FallbackHistoryCursor | None:
    if value is None:
        return None
    if not value or len(value) > 1024:
        raise HTTPException(status_code=422, detail="fallback history cursor is invalid")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        if len(raw) > 512:
            raise ValueError("cursor exceeds its bound")
        payload = json.loads(raw)
        if type(payload) is not dict or set(payload) != {"created_at", "chain_id"}:
            raise ValueError("cursor shape differs")
        if type(payload["created_at"]) is not str or type(payload["chain_id"]) is not str:
            raise TypeError("cursor values differ")
        return FallbackHistoryCursor(payload["created_at"], payload["chain_id"])
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="fallback history cursor is invalid") from exc


def _encode_history_cursor(cursor: FallbackHistoryCursor | None) -> str | None:
    if cursor is None:
        return None
    raw = json.dumps(
        {"chain_id": cursor.chain_id, "created_at": cursor.created_at},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@settings_router.get(
    "/fallback-receipts",
    response_model=FallbackReceiptHistoryResponse,
)
def get_fallback_receipts(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1024),
) -> FallbackReceiptHistoryResponse:
    owner_id = getattr(request.state, "user_id", None)
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise HTTPException(status_code=401, detail="operator identity is required")
    try:
        page = ResearchSpendLedger(default_research_spend_db_path()).fallback_history(
            owner_id.strip(), limit=limit, cursor=_history_cursor(cursor)
        )
    except HTTPException:
        raise
    except (LedgerIntegrityError, sqlite3.Error, OSError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="fallback receipt history is unavailable",
        ) from exc
    return FallbackReceiptHistoryResponse(
        items=[
            FallbackReceiptChainResponse(
                chain_id=chain.chain_id,
                manifest_sha256=chain.manifest_sha256,
                outcome=chain.outcome.value,
                routes=[
                    FallbackReceiptRouteResponse(
                        fallback_index=route.fallback_index,
                        provider=route.provider,
                        model=route.model,
                        seam_id=route.seam_id,
                        operation=route.operation,
                        projected_max_cents=route.projected_max_cents,
                        state=route.state.value,
                        actual_cents=route.actual_cents,
                        resolved_at=route.resolved_at,
                        settlement_evidence_sha256=route.settlement_evidence_sha256,
                        settlement_intent_sha256=route.settlement_intent_sha256,
                    )
                    for route in chain.routes
                ],
                created_at=chain.created_at,
            )
            for chain in page.items
        ],
        next_cursor=_encode_history_cursor(page.next_cursor),
    )


def register_settings_budget_routes(app: FastAPI) -> None:
    app.include_router(settings_router)
    # Add-model admin (user-added BYOK providers) mounts through the same
    # settings-local seam; see settings_models_admin.py. Local import keeps
    # this file's module surface unchanged for the other open PRs that
    # touch its cost/spend regions.
    from .settings_models_admin import register_settings_models_admin_routes

    register_settings_models_admin_routes(app)


__all__ = [
    "BudgetResponse",
    "BenchmarkMeasurement",
    "BenchmarkReport",
    "ModelDecisionRequest",
    "ModelDecisionResponse",
    "ModelsResponse",
    "PromptCostEstimateRequest",
    "PromptCostEstimateResponse",
    "estimate_prompt_cost",
    "build_model_decision",
    "build_model_decision_candidates",
    "read_operator_budget",
    "register_settings_budget_routes",
    "settings_router",
]
