"""HTTP helpers for ACU capacity gate at investigation start / spin."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request, Response

from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.compute_capacity.acu_meter import (
    CAPACITY_WARN_HEADER,
    CapacityGateResult,
    capacity_exhausted_payload,
    capacity_warning_payload,
    gate_investigation_start,
    lookup_start_acu_row,
    record_investigation_start_acu,
)
from substrate.graph import default_db_path

from .settings_models_admin import request_owner_user_id

_LOCK_TIMEOUT_S = 15.0


def resolve_capacity_owner(request: Request) -> str:
    """Owner for ACU metering — authenticated user, else legacy operator."""
    try:
        return request_owner_user_id(request)
    except HTTPException:
        return "__operator__"


def _db_path() -> str:
    return os.path.expanduser(default_db_path())


def run_capacity_precheck(request: Request) -> CapacityGateResult:
    """Read+evaluate under write lock so soft/hard see a consistent row.

    Creates nothing on refuse; may materialize later on successful record.
    """
    owner = resolve_capacity_owner(request)
    db = _db_path()
    try:
        with connect_write(
            db, purpose="compute-capacity:gate", timeout_s=_LOCK_TIMEOUT_S
        ) as con:
            gate = gate_investigation_start(con, owner)
    except WriteLockTimeout as exc:
        raise HTTPException(status_code=503, detail="graph_busy_retry") from exc
    if gate.verdict == "hard_refuse":
        raise HTTPException(
            status_code=429, detail=capacity_exhausted_payload(gate)
        )
    return gate


def commit_start_acu(
    request: Request,
    *,
    investigation_id: str,
    reason: str,
) -> CapacityGateResult:
    """Gate and record 1 ACU BEFORE the start is appended or broadcast.

    Idempotent on investigation id. The hard gate is re-evaluated under the
    same writer lock as the insert, so starts racing past the precheck cannot
    both charge beyond the cap. Callers must not start the run unless this
    returns: a 503 or 429 here means nothing started and nothing was charged.
    """
    owner = resolve_capacity_owner(request)
    db = _db_path()
    try:
        with connect_write(
            db, purpose="compute-capacity:record-acu", timeout_s=_LOCK_TIMEOUT_S
        ) as con:
            # A replay of an already-charged start is not re-gated.
            if lookup_start_acu_row(con, investigation_id) is None:
                gate = gate_investigation_start(con, owner)
                if gate.verdict == "hard_refuse":
                    raise HTTPException(
                        status_code=429, detail=capacity_exhausted_payload(gate)
                    )
            recorded = record_investigation_start_acu(
                con,
                owner_user_id=owner,
                investigation_id=investigation_id,
                reason=reason,
            )
            # Re-evaluate after increment for response warn (may newly soft_over).
            from substrate.compute_capacity.acu_meter import (
                CapacityGateResult as CGR,
            )
            from substrate.compute_capacity.acu_meter import (
                evaluate_with_near_limit,
            )

            ev = evaluate_with_near_limit(recorded.capacity)
            soft = (
                recorded.capacity.enforcement in {"soft", "hard"}
                and (
                    ev.soft_over
                    or (
                        recorded.capacity.used_status == "known"
                        and recorded.capacity.used_compute_units is not None
                        and recorded.capacity.monthly_compute_units > 0
                        and (
                            recorded.capacity.used_compute_units
                            / recorded.capacity.monthly_compute_units
                        )
                        >= 0.8
                    )
                )
            )
            warn = None
            detail = "compute_capacity_ok"
            verdict: Any = "ok"
            if soft:
                verdict = "soft_warn"
                detail = "compute_capacity_soft_warn"
                used = recorded.capacity.used_compute_units
                limit = recorded.capacity.monthly_compute_units
                warn = (
                    f"Antiek-hosted compute near or over monthly capacity "
                    f"({used}/{limit} ACU). BYO Token spend is separate. "
                    f"enforcement={recorded.capacity.enforcement}."
                )
            return CGR(
                verdict=verdict,
                capacity=recorded.capacity,
                evaluation=ev,
                warning=warn,
                detail=detail,
            )
    except WriteLockTimeout as exc:
        raise HTTPException(status_code=503, detail="graph_busy_retry") from exc


def attach_capacity_warn_header(response: Response, gate: CapacityGateResult) -> None:
    if gate.verdict == "soft_warn":
        response.headers[CAPACITY_WARN_HEADER] = gate.detail


def warning_body(gate: CapacityGateResult) -> dict[str, object] | None:
    return capacity_warning_payload(gate)
