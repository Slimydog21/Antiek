"""Operator Settings — model inventory + budget readout + prompt cost projection.

SPR-01 (C288): honest Settings substrate for the operator's model-choice and
budget-awareness needs. Does NOT add models, store API keys, or route via
NotDiamond. Advisory/read surfaces only.

Honesty rules (load-bearing):
  * Spent is ``null`` when no ledger is wired — never invent ``$0 spent``.
  * Cost projection uses ``substrate/dispatch/config.yaml`` tier pricing; when
    rates are ``0.0`` (operator-placeholder), the estimate is ``null`` with an
    explicit note rather than a fake number.
  * Provider list is the live registered set (same source as ``/health``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel, Field

from orchestration.continuous.budget import (
    _ENV_DAILY_CAP,
    DEFAULT_DAILY_CAP_USD,
    DaemonBudget,
    _budget_path,
)
from substrate.antiek_bench import read_latest_scorecard
from substrate.model_routing import (
    NotDiamondAdvisorCandidate,
    NotDiamondAdvisorRecommendation,
    resolve_notdiamond_advisor,
)

settings_router = APIRouter(prefix="/settings", tags=["settings"])

SpentStatus = Literal["known", "unknown", "no_cap"]
TaskKind = Literal[
    "research_question",
    "reading_highlight",
    "midnight_oil",
    "synthesis",
    "verification",
]
RouteMode = Literal["manual", "auto_quality", "auto_balanced", "auto_cost", "auto_latency"]


class ModelRow(BaseModel):
    provider_id: str
    ready: bool
    tier_bindings: list[str] = Field(default_factory=list)
    primary_model: str | None = None
    notes: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelRow]
    count: int
    providers_ready: bool
    source: str = "app.state.registered_providers + dispatch/config.yaml"


class BudgetResponse(BaseModel):
    daily_cap_usd: float | None
    spent_usd: float | None
    remaining_usd: float | None
    spent_status: SpentStatus
    cap_env: str | None
    notes: list[str] = Field(default_factory=list)


class PromptCostEstimateRequest(BaseModel):
    task_kind: TaskKind | None = None
    role: str | None = None
    route_mode: RouteMode = "manual"
    manual_provider: str | None = None
    manual_model: str | None = None
    session_cache_key: str | None = None
    provider: str | None = None
    model: str | None = None
    tier: str | None = Field(
        default="pro",
        description="Dispatch tier name used when model/provider omitted.",
    )
    prompt_chars: int | None = Field(default=None, ge=0)
    input_chars: int = Field(ge=0, default=0)
    expected_output_tokens: int = Field(ge=0, default=500)


class PromptCostCandidate(BaseModel):
    provider: str
    model: str
    tier: str
    fallback_chain_index: int = Field(ge=0)
    estimated_usd_low: float | None
    estimated_usd_high: float | None
    pricing_known: bool
    cache_status: Literal["warm", "cold", "unknown"] = "unknown"
    selection_reason: str


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
    task_kind: str | None = None
    role: str | None = None
    route_mode: RouteMode | None = None
    selected_candidate: PromptCostCandidate | None = None
    candidates: list[PromptCostCandidate] = Field(default_factory=list)


class AntiekBenchBestModelRow(BaseModel):
    task_class: str
    provider: str
    model: str
    quality_score: float
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    cost_per_acceptable_answer: float | None = None
    latency_ms: int | None = None
    route_receipt_ids: list[str] = Field(default_factory=list)


class AntiekBenchLatestResponse(BaseModel):
    available: bool
    scorecard_id: str | None = None
    generated_at: str | None = None
    week_id: str | None = None
    mock_run: bool | None = None
    best_by_task_class: list[AntiekBenchBestModelRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NotDiamondAdvisorResponse(BaseModel):
    estimate: PromptCostEstimateResponse
    recommendation: NotDiamondAdvisorRecommendation


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
    """provider_id → list of tier names where it is primary."""
    out: dict[str, list[str]] = {}
    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict):
        return out
    for tier_name, body in tiers.items():
        if not isinstance(body, dict):
            continue
        provider = body.get("provider")
        if isinstance(provider, str) and provider:
            out.setdefault(provider, []).append(str(tier_name))
    return out


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


def _tier_candidates(
    cfg: dict[str, Any],
    *,
    tier: str | None,
    provider: str | None,
    model: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    tiers = cfg.get("tiers") or {}
    if not isinstance(tiers, dict) or not tiers:
        return [], ["dispatch config has no tiers"]

    chosen_tier = tier if tier and tier in tiers else None
    if chosen_tier is None and (provider or model):
        for name, raw in tiers.items():
            if not isinstance(raw, dict):
                continue
            if provider and raw.get("provider") != provider:
                continue
            if model and raw.get("model") != model:
                continue
            chosen_tier = str(name)
            break
        if chosen_tier is None:
            return [], ["no tier matches requested provider/model"]
    if chosen_tier is None:
        chosen_tier = "pro" if "pro" in tiers else str(next(iter(tiers)))
        notes.append(f"defaulted to tier {chosen_tier!r}")

    raw = tiers.get(chosen_tier)
    if not isinstance(raw, dict):
        return [], notes + ["tier body missing"]

    base_pricing = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else None
    out: list[dict[str, Any]] = []

    def append_candidate(body: dict[str, Any], *, name: str, index: int) -> None:
        candidate_provider = body.get("provider")
        candidate_model = body.get("model")
        if not candidate_provider or not candidate_model:
            return
        pricing = body.get("pricing") if isinstance(body.get("pricing"), dict) else base_pricing
        out.append(
            {
                "tier": name,
                "provider": str(candidate_provider),
                "model": str(candidate_model),
                "pricing": pricing if isinstance(pricing, dict) else None,
                "fallback_chain_index": index,
            }
        )

    append_candidate(raw, name=chosen_tier, index=0)
    current = raw.get("fallback")
    index = 1
    while isinstance(current, dict):
        suffix = "" if index == 1 else str(index)
        append_candidate(current, name=f"{chosen_tier}__fallback{suffix}", index=index)
        current = current.get("fallback")
        index += 1
    return out, notes


def _estimate_candidate(
    candidate: dict[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    cache_warm: bool,
    selection_reason: str,
) -> PromptCostCandidate:
    pricing = candidate.get("pricing")
    if not isinstance(pricing, dict):
        return PromptCostCandidate(
            provider=str(candidate["provider"]),
            model=str(candidate["model"]),
            tier=str(candidate["tier"]),
            fallback_chain_index=int(candidate["fallback_chain_index"]),
            estimated_usd_low=None,
            estimated_usd_high=None,
            pricing_known=False,
            cache_status="unknown",
            selection_reason=selection_reason,
        )

    in_rate = float(pricing.get("input_per_mtok") or 0.0)
    out_rate = float(pricing.get("output_per_mtok") or 0.0)
    cached_rate = float(pricing.get("cached_input_per_mtok") or 0.0)
    if in_rate <= 0.0 and out_rate <= 0.0:
        return PromptCostCandidate(
            provider=str(candidate["provider"]),
            model=str(candidate["model"]),
            tier=str(candidate["tier"]),
            fallback_chain_index=int(candidate["fallback_chain_index"]),
            estimated_usd_low=None,
            estimated_usd_high=None,
            pricing_known=False,
            cache_status="unknown",
            selection_reason=selection_reason,
        )

    effective_input_rate = cached_rate if cache_warm and cached_rate > 0.0 else in_rate
    base = (input_tokens / 1_000_000.0) * effective_input_rate + (
        output_tokens / 1_000_000.0
    ) * out_rate
    return PromptCostCandidate(
        provider=str(candidate["provider"]),
        model=str(candidate["model"]),
        tier=str(candidate["tier"]),
        fallback_chain_index=int(candidate["fallback_chain_index"]),
        estimated_usd_low=round(base * 0.8, 8),
        estimated_usd_high=round(base * 1.2, 8),
        pricing_known=True,
        cache_status="warm" if cache_warm and cached_rate > 0.0 else "cold",
        selection_reason=selection_reason,
    )


def _select_candidate(
    candidates: list[PromptCostCandidate],
    *,
    route_mode: RouteMode,
    manual_provider: str | None,
    manual_model: str | None,
) -> PromptCostCandidate | None:
    if not candidates:
        return None
    if route_mode == "manual":
        for candidate in candidates:
            provider_match = manual_provider is None or candidate.provider == manual_provider
            model_match = manual_model is None or candidate.model == manual_model
            if provider_match and model_match:
                return candidate
        return candidates[0]
    if route_mode == "auto_cost":
        priced = [c for c in candidates if c.estimated_usd_high is not None]
        return min(priced, key=lambda c: c.estimated_usd_high or 0.0) if priced else candidates[0]
    # Until Antiek-bench lands, quality/balanced/latency keep config order.
    return candidates[0]


def estimate_prompt_cost(
    req: PromptCostEstimateRequest,
    *,
    budget: BudgetResponse | None = None,
) -> PromptCostEstimateResponse:
    cfg = _load_dispatch_config()
    request_provider = req.manual_provider or req.provider
    request_model = req.manual_model or req.model
    prompt_chars = req.prompt_chars if req.prompt_chars is not None else req.input_chars
    route_mode = req.route_mode
    raw_candidates, candidate_notes = _tier_candidates(
        cfg,
        tier=req.tier,
        provider=request_provider,
        model=request_model,
    )
    in_tok = _chars_to_tokens(prompt_chars)
    out_tok = req.expected_output_tokens
    projected_candidates = [
        _estimate_candidate(
            candidate,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_warm=bool(req.session_cache_key)
            and int(candidate.get("fallback_chain_index") or 0) == 0,
            selection_reason=route_mode,
        )
        for candidate in raw_candidates
    ]
    selected_candidate = _select_candidate(
        projected_candidates,
        route_mode=route_mode,
        manual_provider=request_provider,
        manual_model=request_model,
    )

    pricing, tier, provider, model, notes = _resolve_tier_pricing(
        cfg,
        tier=req.tier,
        provider=selected_candidate.provider if selected_candidate else request_provider,
        model=selected_candidate.model if selected_candidate else request_model,
    )
    notes = candidate_notes + notes
    if selected_candidate is not None:
        tier = selected_candidate.tier
        provider = selected_candidate.provider
        model = selected_candidate.model
        if not selected_candidate.pricing_known:
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
                task_kind=req.task_kind,
                role=req.role,
                route_mode=route_mode,
                selected_candidate=selected_candidate,
                candidates=projected_candidates,
            )

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
            task_kind=req.task_kind,
            role=req.role,
            route_mode=route_mode,
            selected_candidate=selected_candidate,
            candidates=projected_candidates,
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
            task_kind=req.task_kind,
            role=req.role,
            route_mode=route_mode,
            selected_candidate=selected_candidate,
            candidates=projected_candidates,
        )

    if selected_candidate and selected_candidate.estimated_usd_low is not None:
        low = selected_candidate.estimated_usd_low
        high = selected_candidate.estimated_usd_high or selected_candidate.estimated_usd_low
    else:
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
        task_kind=req.task_kind,
        role=req.role,
        route_mode=route_mode,
        selected_candidate=selected_candidate,
        candidates=projected_candidates,
    )


def _advisor_candidate(candidate: PromptCostCandidate) -> NotDiamondAdvisorCandidate:
    return NotDiamondAdvisorCandidate(
        provider=candidate.provider,
        model=candidate.model,
        tier=candidate.tier,
        estimated_usd_high=candidate.estimated_usd_high,
        pricing_known=candidate.pricing_known,
        cache_status=candidate.cache_status,
    )


def estimate_notdiamond_advisor(req: PromptCostEstimateRequest) -> NotDiamondAdvisorResponse:
    budget = read_operator_budget()
    estimate = estimate_prompt_cost(req, budget=budget)
    candidates = [_advisor_candidate(candidate) for candidate in estimate.candidates]
    selected = _advisor_candidate(estimate.selected_candidate) if estimate.selected_candidate else None
    recommendation = resolve_notdiamond_advisor(
        candidates=candidates,
        local_selected=selected,
        task_kind=req.task_kind,
    )
    return NotDiamondAdvisorResponse(estimate=estimate, recommendation=recommendation)


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
            daily_cap = float(raw)
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


@settings_router.get("/models", response_model=ModelsResponse)
def get_settings_models(request: Request) -> ModelsResponse:
    raw_providers = getattr(request.app.state, "registered_providers", None)
    if isinstance(raw_providers, (set, list, tuple, frozenset)):
        ready_set: set[str] = {str(p) for p in raw_providers}
    else:
        ready_set = set()
    cfg = _load_dispatch_config()
    bindings = _tier_bindings(cfg)

    # Union of registered + config-known providers so Settings can show
    # configured-but-not-ready rows honestly.
    all_ids = sorted(set(ready_set) | set(bindings.keys()))
    rows: list[ModelRow] = []
    for pid in all_ids:
        is_ready = pid in ready_set
        rows.append(
            ModelRow(
                provider_id=pid,
                ready=is_ready,
                tier_bindings=sorted(bindings.get(pid, [])),
                primary_model=_primary_model_for_provider(cfg, pid),
                notes=None if is_ready else "configured in dispatch config but not registered at boot",
            )
        )
    return ModelsResponse(
        models=rows,
        count=len(rows),
        providers_ready=bool(ready_set),
    )


@settings_router.get("/budget", response_model=BudgetResponse)
def get_settings_budget() -> BudgetResponse:
    return read_operator_budget()


@settings_router.post("/prompt-cost-estimate", response_model=PromptCostEstimateResponse)
def post_prompt_cost_estimate(req: PromptCostEstimateRequest) -> PromptCostEstimateResponse:
    budget = read_operator_budget()
    return estimate_prompt_cost(req, budget=budget)


@settings_router.post("/router-advisor/notdiamond", response_model=NotDiamondAdvisorResponse)
def post_notdiamond_advisor(req: PromptCostEstimateRequest) -> NotDiamondAdvisorResponse:
    return estimate_notdiamond_advisor(req)


@settings_router.get("/antiek-bench/latest", response_model=AntiekBenchLatestResponse)
def get_latest_antiek_bench_scorecard() -> AntiekBenchLatestResponse:
    scorecard = read_latest_scorecard()
    if scorecard is None:
        return AntiekBenchLatestResponse(
            available=False,
            notes=["no Antiek-bench scorecard has been written yet"],
        )
    best = scorecard.best_by_task_class()
    return AntiekBenchLatestResponse(
        available=True,
        scorecard_id=scorecard.scorecard_id,
        generated_at=scorecard.generated_at,
        week_id=scorecard.week_id,
        mock_run=scorecard.mock_run,
        best_by_task_class=[
            AntiekBenchBestModelRow(
                task_class=task_class,
                provider=entry.provider,
                model=entry.model,
                quality_score=entry.quality_score,
                estimated_cost_usd=entry.estimated_cost_usd,
                actual_cost_usd=entry.actual_cost_usd,
                cost_per_acceptable_answer=entry.cost_per_acceptable_answer,
                latency_ms=entry.latency_ms,
                route_receipt_ids=entry.route_receipt_ids,
            )
            for task_class, entry in sorted(best.items())
        ],
        notes=scorecard.notes,
    )


def register_settings_budget_routes(app: FastAPI) -> None:
    app.include_router(settings_router)


__all__ = [
    "BudgetResponse",
    "AntiekBenchBestModelRow",
    "AntiekBenchLatestResponse",
    "ModelsResponse",
    "NotDiamondAdvisorResponse",
    "PromptCostCandidate",
    "PromptCostEstimateRequest",
    "PromptCostEstimateResponse",
    "estimate_notdiamond_advisor",
    "estimate_prompt_cost",
    "read_operator_budget",
    "register_settings_budget_routes",
    "settings_router",
]
