"""Operator Settings — model inventory + budget readout + prompt cost projection.

SPR-01 (C288): honest Settings substrate for the operator's model-choice and
budget-awareness needs. Does NOT add models, store API keys, or route via
NotDiamond. Advisory/read surfaces only.

Honesty rules (load-bearing):
  * Spent/remaining are ``null`` when no ledger is wired — never invent ``$0``.
  * Sidecar ``spent_usd`` is a **reserved estimate** (fixed per-spawn holds),
    not settled provider cost. Surfaces label that basis explicitly.
  * Display (Settings) cap and enforcement (daemon) cap are both reported when
    they diverge — never pretend one number is both.
  * Remaining under the display cap is **signed** (negative when over budget)
    so overrun magnitude is never clamped away.
  * Cost projection uses ``substrate/dispatch/config.yaml`` tier pricing; when
    rates are ``0.0`` (operator-placeholder), the estimate is ``null`` with an
    explicit note rather than a fake number.
  * Provider list is the live registered set (same source as ``/health``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel, Field

from orchestration.continuous.budget import (
    _ENV_DAILY_CAP,
    DEFAULT_DAILY_CAP_USD,
    _budget_path,
)

settings_router = APIRouter(prefix="/settings", tags=["settings"])

SpentStatus = Literal["known", "unknown", "no_cap"]
SpendBasis = Literal["unknown", "reserved_estimate"]


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
    """Operator budget readout.

    ``daily_cap_usd`` is the Settings/display cap. ``enforcement_cap_usd`` is
    what the continuous daemon actually enforces. ``spent_usd`` mirrors
    ``reserved_estimated_usd`` for back-compat; both are reserved holds, not
    settled provider cost (see ``spend_basis``). ``remaining_usd`` is signed:
    ``display_cap - reserved`` (negative when over the display cap).
    """

    daily_cap_usd: float | None
    spent_usd: float | None
    remaining_usd: float | None
    spent_status: SpentStatus
    cap_env: str | None
    notes: list[str] = Field(default_factory=list)
    # Honesty fields (additive; older clients ignore them).
    reserved_estimated_usd: float | None = None
    spend_basis: SpendBasis = "unknown"
    enforcement_cap_usd: float | None = None
    enforcement_cap_env: str | None = None
    caps_aligned: bool | None = None
    over_budget: bool | None = None


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


def _resolve_display_cap(notes: list[str]) -> tuple[float, str | None]:
    """Settings/display cap: operator env preferred, then daemon env, then default."""
    for env_name in ("ANTIEK_OPERATOR_BUDGET_USD", _ENV_DAILY_CAP):
        raw = os.environ.get(env_name)
        if raw is None or raw.strip() == "":
            continue
        try:
            return float(raw), env_name
        except ValueError:
            notes.append(f"{env_name} is not a float; ignored")
    notes.append(
        f"no ANTIEK_OPERATOR_BUDGET_USD / {_ENV_DAILY_CAP}; "
        f"showing daemon default cap ${DEFAULT_DAILY_CAP_USD:.2f}/day as reference"
    )
    return DEFAULT_DAILY_CAP_USD, None


def _resolve_enforcement_cap(notes: list[str]) -> tuple[float, str | None]:
    """Cap the continuous daemon actually enforces (never the operator-only env)."""
    raw = os.environ.get(_ENV_DAILY_CAP)
    if raw is not None and raw.strip() != "":
        try:
            return float(raw), _ENV_DAILY_CAP
        except ValueError:
            notes.append(f"{_ENV_DAILY_CAP} is not a float; enforcement uses default")
    return DEFAULT_DAILY_CAP_USD, None


def _read_sidecar_reserved_usd() -> float | None:
    """Read reserved-estimate spend from the daemon sidecar JSON.

    Does **not** call ``DaemonBudget.remaining_today()`` (that re-bases on
    whatever cap the DaemonBudget was constructed with) and does **not** edit
    ``orchestration/continuous/budget.py`` (protected by the §7.4 tripwire).
    Absent file → ``None`` (unknown), never a fabricated zero.
    """
    path = _budget_path()
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("budget sidecar is not a JSON object")
    return max(0.0, float(raw.get("spent_usd", 0.0)))


def read_operator_budget() -> BudgetResponse:
    """Read display/enforcement caps + reserved-estimate spend honestly."""
    notes: list[str] = []
    daily_cap, cap_env = _resolve_display_cap(notes)
    enforcement_cap, enforcement_cap_env = _resolve_enforcement_cap(notes)
    caps_aligned = abs(float(daily_cap) - float(enforcement_cap)) < 1e-9
    if not caps_aligned:
        notes.append(
            f"display cap ${float(daily_cap):.2f}/day"
            f" ({cap_env or 'default'}) differs from enforcement cap"
            f" ${float(enforcement_cap):.2f}/day"
            f" ({enforcement_cap_env or 'daemon default'}) —"
            f" daemon halt uses enforcement; Settings bar uses display"
        )

    reserved: float | None = None
    remaining: float | None = None
    spent_status: SpentStatus = "unknown"
    spend_basis: SpendBasis = "unknown"
    over_budget: bool | None = None
    try:
        reserved = _read_sidecar_reserved_usd()
        if reserved is None:
            notes.append("spent ledger unavailable: daemon sidecar missing")
        else:
            # Signed remaining on the Settings/display cap — no clamp.
            remaining = float(daily_cap) - float(reserved)
            spent_status = "known"
            spend_basis = "reserved_estimate"
            over_budget = remaining < 0.0
            notes.append(
                "reserved_estimated_usd from continuous-daemon sidecar "
                "(fixed per-spawn holds, not settled provider cost)"
            )
            if over_budget:
                notes.append(
                    f"over display budget by ${abs(remaining):.4f} "
                    f"(remaining_usd is signed, not clamped to 0)"
                )
    except Exception as exc:  # noqa: BLE001 — honesty over crash
        reserved = None
        remaining = None
        spent_status = "unknown"
        spend_basis = "unknown"
        over_budget = None
        notes.append(f"spent ledger unavailable: {type(exc).__name__}")

    return BudgetResponse(
        daily_cap_usd=daily_cap,
        # Back-compat alias: same number as reserved_estimated_usd.
        spent_usd=reserved,
        remaining_usd=remaining,
        spent_status=spent_status,
        cap_env=cap_env,
        notes=notes,
        reserved_estimated_usd=reserved,
        spend_basis=spend_basis,
        enforcement_cap_usd=enforcement_cap,
        enforcement_cap_env=enforcement_cap_env,
        caps_aligned=caps_aligned,
        over_budget=over_budget,
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


def register_settings_budget_routes(app: FastAPI) -> None:
    app.include_router(settings_router)


__all__ = [
    "BudgetResponse",
    "ModelsResponse",
    "PromptCostEstimateRequest",
    "PromptCostEstimateResponse",
    "estimate_prompt_cost",
    "read_operator_budget",
    "register_settings_budget_routes",
    "settings_router",
]
