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

settings_router = APIRouter(prefix="/settings", tags=["settings"])

SpentStatus = Literal["known", "unknown", "no_cap"]


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


class AntiekBenchLeaderboardResponse(BaseModel):
    """Settings-facing Antiek-bench weekly leaderboard (offline runs only)."""

    week_id: str
    models: list[dict[str, Any]] = Field(default_factory=list)
    task_classes: list[str] = Field(default_factory=list)
    run_count: int = 0
    suite_versions: list[str] = Field(default_factory=list)
    recommended_model_id: str | None = None
    recommended_mean_score: float | None = None
    view_format: str = "html"
    settings_panel: str = "antiek_bench_weekly"
    source: str = "antiek_bench.offline_runs"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.get(
    "/antiek-bench/leaderboard",
    response_model=AntiekBenchLeaderboardResponse,
)
def get_antiek_bench_leaderboard(
    request: Request,
    week_id: str,
    include_html: bool = False,
) -> AntiekBenchLeaderboardResponse:
    """Return weekly model/task-class leaderboard from offline bench store.

    Store resolution:
    1. ``app.state.antiek_bench_store`` when injected (tests / configured app)
    2. engagement/usage bench store when present
    3. honest empty snapshot when neither is available

    Does not run live multi-provider benchmarks. HTML-first when include_html.
    """
    store = getattr(request.app.state, "antiek_bench_store", None)
    notes: list[str] = []
    if store is None:
        try:
            from .engagement_routes import get_bench_usage_store

            store = get_bench_usage_store(create_if_missing=False)
        except Exception:
            store = None
    if store is None:
        return AntiekBenchLeaderboardResponse(
            week_id=week_id.strip(),
            view_format="html",
            notes=[
                "antiek_bench_store not configured on app.state "
                "(and no engagement usage store); "
                "no offline runs available for leaderboard"
            ],
        )
    from substrate.antiek_bench import settings_leaderboard_payload

    payload = settings_leaderboard_payload(
        week_id, store=store, include_html=include_html
    )
    return AntiekBenchLeaderboardResponse(
        week_id=str(payload.get("week_id") or week_id),
        models=list(payload.get("models") or []),
        task_classes=list(payload.get("task_classes") or []),
        run_count=int(payload.get("run_count") or 0),
        suite_versions=list(payload.get("suite_versions") or []),
        recommended_model_id=payload.get("recommended_model_id"),
        recommended_mean_score=payload.get("recommended_mean_score"),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "antiek_bench_weekly"),
        source=str(payload.get("source") or "antiek_bench.offline_runs"),
        notes=list(payload.get("notes") or notes),
        html=payload.get("html"),
    )


class AntiekBenchUsageSummaryResponse(BaseModel):
    """Settings-facing weekly usage summary from recorded engagement events."""

    event_count: int = 0
    by_task_class: dict[str, dict[str, int]] = Field(default_factory=dict)
    view_format: str = "html"
    settings_panel: str = "antiek_bench_usage_weekly"
    source: str = "antiek_bench.usage_events"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.get(
    "/antiek-bench/usage-summary",
    response_model=AntiekBenchUsageSummaryResponse,
)
def get_antiek_bench_usage_summary(
    request: Request,
    include_html: bool = False,
) -> AntiekBenchUsageSummaryResponse:
    """Return weekly usage summary derived from shipped ``weekly_usage_summary``.

    Store resolution (honest process-local limitation):
    1. ``app.state.antiek_bench_store`` when injected (tests / configured app)
    2. engagement flywheel process-local usage store when present
    3. empty summary with note when neither is available

    Does not run live multi-provider Antiek-bench.
    """
    from substrate.antiek_bench import settings_usage_summary_payload

    store = getattr(request.app.state, "antiek_bench_store", None)
    notes: list[str] = []
    if store is None:
        # Share process-local store with engagement complete-flywheel when possible.
        try:
            from .engagement_routes import get_bench_usage_store

            store = get_bench_usage_store(create_if_missing=False)
        except Exception:
            store = None
    if store is None:
        return AntiekBenchUsageSummaryResponse(
            notes=[
                "No antiek_bench_store / engagement usage store configured; "
                "usage summary is empty until flywheel records events or a store is injected"
            ],
            view_format="html",
        )

    payload = settings_usage_summary_payload(store=store, include_html=include_html)
    return AntiekBenchUsageSummaryResponse(
        event_count=int(payload.get("event_count") or 0),
        by_task_class=dict(payload.get("by_task_class") or {}),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "antiek_bench_usage_weekly"),
        source=str(payload.get("source") or "antiek_bench.usage_events"),
        notes=list(payload.get("notes") or notes),
        html=payload.get("html"),
    )


class AntiekBenchSuiteProposalResponse(BaseModel):
    """Settings-facing suite rewrite proposal (proposed only; never auto-promote)."""

    has_proposal: bool = False
    proposal_id: str | None = None
    status: str | None = None
    base_suite_version: str | None = None
    proposed_suite_version: str | None = None
    active_suite_version: str | None = None
    active_suite_unchanged: bool = True
    auto_promoted: bool = False
    rationale: str | None = None
    added_item_ids: list[str] = Field(default_factory=list)
    event_count: int = 0
    view_format: str = "html"
    settings_panel: str = "antiek_bench_suite_proposal"
    source: str = "antiek_bench.propose_from_recorded_usage"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.get(
    "/antiek-bench/suite-proposal",
    response_model=AntiekBenchSuiteProposalResponse,
)
def get_antiek_bench_suite_proposal(
    request: Request,
    include_html: bool = False,
) -> AntiekBenchSuiteProposalResponse:
    """Return suite rewrite *proposal* from recorded usage events.

    Calls shipped ``propose_from_recorded_usage``. Does **not** call
    ``approve_and_promote``. Empty usage yields honest empty (no fabricated suite).

    Store resolution matches usage-summary:
    1. ``app.state.antiek_bench_store`` when injected
    2. engagement flywheel process-local usage store when present
    3. honest empty when neither is available
    """
    from substrate.antiek_bench import settings_suite_proposal_payload

    store = getattr(request.app.state, "antiek_bench_store", None)
    if store is None:
        try:
            from .engagement_routes import get_bench_usage_store

            store = get_bench_usage_store(create_if_missing=False)
        except Exception:
            store = None
    if store is None:
        return AntiekBenchSuiteProposalResponse(
            notes=[
                "No antiek_bench_store / engagement usage store configured; "
                "suite proposal is empty until flywheel records events or a store is injected"
            ],
            view_format="html",
            auto_promoted=False,
            active_suite_unchanged=True,
        )

    payload = settings_suite_proposal_payload(
        store=store, include_html=include_html
    )
    return AntiekBenchSuiteProposalResponse(
        has_proposal=bool(payload.get("has_proposal")),
        proposal_id=payload.get("proposal_id"),
        status=payload.get("status"),
        base_suite_version=payload.get("base_suite_version"),
        proposed_suite_version=payload.get("proposed_suite_version"),
        active_suite_version=payload.get("active_suite_version"),
        active_suite_unchanged=bool(payload.get("active_suite_unchanged", True)),
        auto_promoted=bool(payload.get("auto_promoted", False)),
        rationale=payload.get("rationale"),
        added_item_ids=list(payload.get("added_item_ids") or []),
        event_count=int(payload.get("event_count") or 0),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(
            payload.get("settings_panel") or "antiek_bench_suite_proposal"
        ),
        source=str(
            payload.get("source") or "antiek_bench.propose_from_recorded_usage"
        ),
        notes=list(payload.get("notes") or []),
        html=payload.get("html"),
    )


class AntiekBenchSuiteApproveRequest(BaseModel):
    """Explicit operator approve/reject for a suite rewrite proposal."""

    proposal_id: str = Field(min_length=1)
    approve: bool = True
    include_html: bool = False


class AntiekBenchSuiteApproveResponse(BaseModel):
    """Result of explicit approve_and_promote (never from GET propose alone)."""

    ok: bool = False
    proposal_id: str | None = None
    status: str | None = None
    approved: bool = False
    promoted: bool = False
    active_suite_version: str | None = None
    active_suite_before: str | None = None
    proposed_suite_version: str | None = None
    view_format: str = "html"
    settings_panel: str = "antiek_bench_suite_approve"
    source: str = "antiek_bench.approve_and_promote"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.post(
    "/antiek-bench/suite-proposal/approve",
    response_model=AntiekBenchSuiteApproveResponse,
)
def post_antiek_bench_suite_approve(
    request: Request,
    body: AntiekBenchSuiteApproveRequest,
) -> AntiekBenchSuiteApproveResponse:
    """Explicit operator gate for suite promote/reject.

    Does **not** run on GET propose. Reject leaves active suite unchanged.
    """
    from substrate.antiek_bench import settings_approve_suite_proposal_payload

    store = getattr(request.app.state, "antiek_bench_store", None)
    if store is None:
        try:
            from .engagement_routes import get_bench_usage_store

            store = get_bench_usage_store(create_if_missing=False)
        except Exception:
            store = None
    if store is None:
        return AntiekBenchSuiteApproveResponse(
            ok=False,
            proposal_id=body.proposal_id,
            notes=[
                "No antiek_bench_store / engagement usage store configured; "
                "cannot approve/promote without a store holding the proposal"
            ],
            view_format="html",
        )

    registry = getattr(request.app.state, "antiek_bench_registry", None)
    try:
        payload = settings_approve_suite_proposal_payload(
            body.proposal_id,
            store=store,
            registry=registry,
            approve=body.approve,
            include_html=body.include_html,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AntiekBenchSuiteApproveResponse(
        ok=bool(payload.get("ok")),
        proposal_id=payload.get("proposal_id"),
        status=payload.get("status"),
        approved=bool(payload.get("approved")),
        promoted=bool(payload.get("promoted")),
        active_suite_version=payload.get("active_suite_version"),
        active_suite_before=payload.get("active_suite_before"),
        proposed_suite_version=payload.get("proposed_suite_version"),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(
            payload.get("settings_panel") or "antiek_bench_suite_approve"
        ),
        source=str(payload.get("source") or "antiek_bench.approve_and_promote"),
        notes=list(payload.get("notes") or []),
        html=payload.get("html"),
    )


class NotDiamondAdvisoryResponse(BaseModel):
    """Settings-facing NotDiamond advisory posture (offline; never authority)."""

    advisory_allowed: bool = True
    advisory_verdict: str = "GO"
    authority_allowed: bool = False
    authority_rejected: bool = True
    authority_verdict: str = "REJECT"
    dispatch_owner: str = "hermes_primary_plus_decision_tree"
    notdiamond_is_dispatch_authority: bool = False
    kill_switch_env: str = "ANTIEK_NOTDIAMOND"
    kill_switch_enabled: bool = False
    default_off: bool = True
    view_format: str = "html"
    settings_panel: str = "notdiamond_advisory"
    source: str = "docs/htmlspec/notdiamond-verdict/VERDICT.md"
    verdict_date: str = "2026-07-09"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.get(
    "/notdiamond/advisory",
    response_model=NotDiamondAdvisoryResponse,
)
def get_notdiamond_advisory(include_html: bool = False) -> NotDiamondAdvisoryResponse:
    """Return offline NotDiamond advisory posture for Settings.

    Never calls NotDiamond HTTP. Never claims ND owns dispatch.
    Authority is always rejected; advisory may be GO with kill-switch default off.
    """
    from substrate.notdiamond_advisory import notdiamond_advisory_payload

    payload = notdiamond_advisory_payload(include_html=include_html)
    return NotDiamondAdvisoryResponse(
        advisory_allowed=bool(payload.get("advisory_allowed")),
        advisory_verdict=str(payload.get("advisory_verdict") or "GO"),
        authority_allowed=bool(payload.get("authority_allowed")),
        authority_rejected=bool(payload.get("authority_rejected")),
        authority_verdict=str(payload.get("authority_verdict") or "REJECT"),
        dispatch_owner=str(
            payload.get("dispatch_owner") or "hermes_primary_plus_decision_tree"
        ),
        notdiamond_is_dispatch_authority=bool(
            payload.get("notdiamond_is_dispatch_authority")
        ),
        kill_switch_env=str(payload.get("kill_switch_env") or "ANTIEK_NOTDIAMOND"),
        kill_switch_enabled=bool(payload.get("kill_switch_enabled")),
        default_off=bool(payload.get("default_off", True)),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "notdiamond_advisory"),
        source=str(payload.get("source") or ""),
        verdict_date=str(payload.get("verdict_date") or ""),
        notes=list(payload.get("notes") or []),
        html=payload.get("html"),
    )


class DecisionTreeSelectionRequest(BaseModel):
    """Install operator decision-tree driver for this process."""

    model_id: str = Field(min_length=1)
    provider_id: str | None = Field(
        default=None,
        description="Required when the model is not yet in the process registry.",
    )


class DecisionTreeSelectionResponse(BaseModel):
    model_id: str | None = None
    provider_id: str | None = None
    installed: bool = False
    notes: list[str] = Field(default_factory=list)
    source: str = "substrate.model_registration.process_registry"


@settings_router.get(
    "/decision-tree",
    response_model=DecisionTreeSelectionResponse,
)
def get_decision_tree_selection() -> DecisionTreeSelectionResponse:
    """Read process-local decision-tree selection (may be empty)."""
    from substrate.model_registration import read_decision_tree_selection

    raw = read_decision_tree_selection()
    return DecisionTreeSelectionResponse(
        model_id=raw.get("model_id"),
        provider_id=raw.get("provider_id"),
        installed=bool(raw.get("installed")),
        notes=list(raw.get("notes") or []),
    )


@settings_router.post(
    "/decision-tree",
    response_model=DecisionTreeSelectionResponse,
)
def post_decision_tree_selection(
    req: DecisionTreeSelectionRequest,
) -> DecisionTreeSelectionResponse:
    """Install model into process-local decision-tree registry.

    Honest limitation: selection is process-local. The API process that
    serves this route must be the same process that runs dispatch for the
    override to apply (or each worker must receive the same install).
    """
    from substrate.model_registration import install_decision_tree_selection

    try:
        result = install_decision_tree_selection(
            req.model_id,
            provider_id=req.provider_id,
            ensure_registered=True,
        )
    except (KeyError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DecisionTreeSelectionResponse(
        model_id=result.model_id,
        provider_id=result.provider_id,
        installed=result.installed,
        notes=list(result.notes),
    )


@settings_router.delete(
    "/decision-tree",
    response_model=DecisionTreeSelectionResponse,
)
def delete_decision_tree_selection() -> DecisionTreeSelectionResponse:
    """Clear process-local decision-tree selection."""
    from substrate.model_registration import clear_decision_tree_selection

    raw = clear_decision_tree_selection()
    return DecisionTreeSelectionResponse(
        model_id=raw.get("model_id"),
        provider_id=raw.get("provider_id"),
        installed=bool(raw.get("installed")),
        notes=list(raw.get("notes") or []),
    )


class DepthTierApplyRequest(BaseModel):
    """Select flash | pro | wrestle depth tier (optional driver install)."""

    depth_tier: str = Field(min_length=1)
    model_id: str | None = None
    provider_id: str | None = None
    install_driver: bool = False
    include_html: bool = False


class DepthTierResponse(BaseModel):
    active_depth_tier: str | None = None
    active_preset: dict[str, Any] | None = None
    presets: list[dict[str, Any]] = Field(default_factory=list)
    projection_hints: dict[str, Any] | None = None
    decision_tree_install: dict[str, Any] | None = None
    view_format: str = "html"
    settings_panel: str = "depth_tier_presets"
    source: str = "substrate.model_registration.depth_tiers"
    notes: list[str] = Field(default_factory=list)
    html: str | None = None


@settings_router.get("/antiek-bench/dogfood-fixtures")
def get_antiek_bench_dogfood_fixtures(include_html: bool = False) -> dict[str, Any]:
    """List competitive dogfood fixtures (offline; never auto-promote)."""
    from substrate.antiek_bench import dogfood_fixture_payload

    return dogfood_fixture_payload(include_html=include_html)


@settings_router.get(
    "/depth-tier",
    response_model=DepthTierResponse,
)
def get_depth_tier(include_html: bool = False) -> DepthTierResponse:
    """List depth-tier presets and process-local active selection."""
    from substrate.model_registration import depth_tiers_settings_payload

    payload = depth_tiers_settings_payload(include_html=include_html)
    return DepthTierResponse(
        active_depth_tier=payload.get("active_depth_tier"),
        active_preset=payload.get("active_preset"),
        presets=list(payload.get("presets") or []),
        projection_hints=payload.get("projection_hints"),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "depth_tier_presets"),
        source=str(payload.get("source") or ""),
        notes=list(payload.get("notes") or []),
        html=payload.get("html"),
    )


@settings_router.post(
    "/depth-tier",
    response_model=DepthTierResponse,
)
def post_depth_tier(req: DepthTierApplyRequest) -> DepthTierResponse:
    """Apply depth tier (+ optional decision-tree driver install)."""
    from substrate.model_registration import (
        apply_depth_tier,
        depth_tiers_settings_payload,
    )

    try:
        applied = apply_depth_tier(
            req.depth_tier,
            model_id=req.model_id,
            provider_id=req.provider_id,
            install_driver=req.install_driver,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = depth_tiers_settings_payload(include_html=req.include_html)
    return DepthTierResponse(
        active_depth_tier=payload.get("active_depth_tier"),
        active_preset=payload.get("active_preset"),
        presets=list(payload.get("presets") or []),
        projection_hints=applied.get("projection_hints")
        or payload.get("projection_hints"),
        decision_tree_install=applied.get("decision_tree_install"),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "depth_tier_presets"),
        source=str(payload.get("source") or ""),
        notes=list(applied.get("notes") or []) + list(payload.get("notes") or []),
        html=payload.get("html"),
    )


@settings_router.delete(
    "/depth-tier",
    response_model=DepthTierResponse,
)
def delete_depth_tier(include_html: bool = False) -> DepthTierResponse:
    """Clear process-local depth tier selection."""
    from substrate.model_registration import (
        clear_active_depth_tier,
        depth_tiers_settings_payload,
    )

    clear_active_depth_tier()
    payload = depth_tiers_settings_payload(include_html=include_html)
    payload["notes"] = list(payload.get("notes") or []) + ["depth tier cleared"]
    return DepthTierResponse(
        active_depth_tier=payload.get("active_depth_tier"),
        active_preset=payload.get("active_preset"),
        presets=list(payload.get("presets") or []),
        projection_hints=payload.get("projection_hints"),
        view_format=str(payload.get("view_format") or "html"),
        settings_panel=str(payload.get("settings_panel") or "depth_tier_presets"),
        source=str(payload.get("source") or ""),
        notes=list(payload.get("notes") or []),
        html=payload.get("html"),
    )


def register_settings_budget_routes(app: FastAPI) -> None:
    app.include_router(settings_router)


__all__ = [
    "AntiekBenchLeaderboardResponse",
    "AntiekBenchSuiteApproveRequest",
    "AntiekBenchSuiteApproveResponse",
    "AntiekBenchSuiteProposalResponse",
    "AntiekBenchUsageSummaryResponse",
    "BudgetResponse",
    "DecisionTreeSelectionRequest",
    "DecisionTreeSelectionResponse",
    "DepthTierApplyRequest",
    "DepthTierResponse",
    "ModelsResponse",
    "PromptCostEstimateRequest",
    "PromptCostEstimateResponse",
    "delete_decision_tree_selection",
    "delete_depth_tier",
    "estimate_prompt_cost",
    "NotDiamondAdvisoryResponse",
    "get_antiek_bench_leaderboard",
    "get_antiek_bench_suite_proposal",
    "get_antiek_bench_usage_summary",
    "get_decision_tree_selection",
    "get_depth_tier",
    "get_notdiamond_advisory",
    "post_antiek_bench_suite_approve",
    "post_decision_tree_selection",
    "post_depth_tier",
    "read_operator_budget",
    "register_settings_budget_routes",
    "settings_router",
]
