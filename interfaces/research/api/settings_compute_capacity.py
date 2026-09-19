"""Settings — Antiek-hosted agent compute capacity slider (BYOT pillar).

``GET  /settings/compute-capacity`` — current owner's tier + monthly ACU.
``PUT  /settings/compute-capacity`` — set tier and/or monthly units.

Aligns with vision: BYO Token (usage ledger elsewhere) vs Antiek-managed
compute quota here. No fake billing; used stays unmetered until a meter
exists. Enforcement is env-gated (``ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT``).
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import WriteLockTimeout, connect_read, connect_write
from substrate.compute_capacity import (
    CAPACITY_TIERS,
    evaluate_capacity,
    get_capacity,
    set_capacity,
    tier_default_units,
)
from substrate.graph import default_db_path

from .settings_models_admin import request_owner_user_id

settings_compute_capacity_router = APIRouter(prefix="/settings", tags=["settings"])

_LOCK_TIMEOUT_S = 15.0
CapacityTierWire = Literal["starter", "standard", "power", "custom"]


class ComputeCapacityResponse(BaseModel):
    owner_user_id: str
    tier: CapacityTierWire
    monthly_compute_units: int
    used_compute_units: int | None
    used_status: Literal["unmetered", "known"]
    enforcement: Literal["off", "soft", "hard"]
    updated_at: str | None
    is_default: bool
    tier_presets: dict[str, int]
    evaluation: dict[str, Any]
    note: str


class SetComputeCapacityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: CapacityTierWire
    monthly_compute_units: int | None = Field(default=None, ge=0, le=50_000)


def _resolve_db_path() -> str:
    return os.path.expanduser(default_db_path())


def _to_response(cap: Any) -> ComputeCapacityResponse:
    ev = evaluate_capacity(cap)
    return ComputeCapacityResponse(
        owner_user_id=cap.owner_user_id,
        tier=cap.tier,
        monthly_compute_units=cap.monthly_compute_units,
        used_compute_units=cap.used_compute_units,
        used_status=cap.used_status,
        enforcement=cap.enforcement,
        updated_at=cap.updated_at,
        is_default=cap.is_default,
        tier_presets={
            t: units
            for t in CAPACITY_TIERS
            if (units := tier_default_units(t)) is not None
        },
        evaluation={
            "allowed": ev.allowed,
            "soft_over": ev.soft_over,
            "would_hard_block": ev.would_hard_block,
            "note": ev.note,
        },
        note=(
            "Antiek-hosted agent compute quota (ACU/month). "
            "BYO Token spend is separate (Settings → Usage). "
            "No BYO CPU by default; used units unmetered until meter ships. "
            "No fake billing."
        ),
    )


@settings_compute_capacity_router.get(
    "/compute-capacity",
    response_model=ComputeCapacityResponse,
)
async def get_compute_capacity(request: Request) -> ComputeCapacityResponse:
    owner = request_owner_user_id(request)
    db = _resolve_db_path()
    if not os.path.exists(db):
        # No store yet — honest default without creating the DB.
        from substrate.compute_capacity.store import _default_capacity, enforcement_from_env

        return _to_response(_default_capacity(owner, enforcement_from_env()))
    con = connect_read(db)
    try:
        return _to_response(get_capacity(con, owner))
    finally:
        con.close()


@settings_compute_capacity_router.put(
    "/compute-capacity",
    response_model=ComputeCapacityResponse,
)
async def put_compute_capacity(
    request: Request,
    body: SetComputeCapacityRequest,
) -> ComputeCapacityResponse:
    owner = request_owner_user_id(request)
    db = _resolve_db_path()
    try:
        with connect_write(
            db, purpose="settings/compute-capacity:set", timeout_s=_LOCK_TIMEOUT_S
        ) as con:
            try:
                cap = set_capacity(
                    con,
                    owner_user_id=owner,
                    tier=body.tier,
                    monthly_compute_units=body.monthly_compute_units,
                )
            except ValueError as exc:
                code = str(exc)
                if code == "invalid_tier":
                    raise HTTPException(status_code=400, detail="invalid_tier") from exc
                if code == "custom_requires_units":
                    raise HTTPException(
                        status_code=400, detail="custom_requires_units"
                    ) from exc
                if code == "units_out_of_range":
                    raise HTTPException(
                        status_code=400, detail="units_out_of_range"
                    ) from exc
                raise HTTPException(status_code=400, detail="invalid_capacity") from exc
    except WriteLockTimeout as exc:
        raise HTTPException(
            status_code=503, detail="graph_busy_retry"
        ) from exc
    return _to_response(cap)


def register_settings_compute_capacity_routes(app: FastAPI) -> None:
    app.include_router(settings_compute_capacity_router)
