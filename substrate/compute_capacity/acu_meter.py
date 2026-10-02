"""ACU metering for Antiek-hosted agent compute.

Doctrine (docs/decisions/byot-capacity-slider-2026-09-18.md + this module):
BYO Token spend stays on the usage ledger. ACU meters *Antiek-managed*
orchestration / retrieval / event-log CPU committed when an investigation
starts — not LLM cents, not wall-clock dollars.

Heuristic (honest, deliberate — not fake pricing):

    1 ACU = one investigation start
            (``POST /investigations`` or ``POST /books/.../spin-research``)

    + floor(wall_seconds / 300) ACU on terminal finish (complete / fail /
      halt-after-start / cancel), capped at 12 ACU per investigation.
      Wall clock is start-ledger ``recorded_at`` → finish ``now`` (UTC).
      Under one 300s quantum → +0 (start charge already covers short runs).

Rationale: at start we commit host CPU (orchestrator spawn, DuckDB
contention, retrieval, event append). Dispatch ``latency_ms`` and role-call
counts are BYOT-adjacent and incomplete at the pre-commit gate; charging
flat 1 ACU at start makes soft-warn / hard-refuse decidable *before* work
begins. Wall-time top-up meters long-running host work without inventing
dollars or Stripe prices (cites #3139/#3140/#3184).

Idempotency: start row keys on ``investigation_id``; wall top-up keys on
``{investigation_id}#wall_topup`` so completion replays do not double-charge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from substrate.compute_capacity.store import (
    CapacityEvaluation,
    ComputeCapacity,
    ensure_table,
    evaluate_capacity,
    get_capacity,
    set_capacity,
)
from substrate.contracts.anti_ek_honesty import assert_capacity_exhausted_shape

_log = logging.getLogger("antiek.compute_capacity.acu_meter")

ACU_PER_INVESTIGATION_START = 1
# Completion top-up: +1 ACU per full quantum of wall time (not dollars).
WALL_TOPUP_QUANTUM_SECONDS = 300  # 5 minutes
WALL_TOPUP_MAX_ACU = 12  # cap so a stuck run cannot drain the month
WALL_TOPUP_REASON = "investigation_wall_topup"
WALL_TOPUP_ID_SUFFIX = "#wall_topup"
NEAR_LIMIT_RATIO = 0.8  # soft warn when used/monthly >= this
CAPACITY_WARN_HEADER = "X-Antiek-Capacity-Warn"

GateVerdict = Literal["ok", "soft_warn", "hard_refuse"]


@dataclass(frozen=True)
class AcuRecordResult:
    owner_user_id: str
    investigation_id: str
    acu_units: int
    replayed: bool
    capacity: ComputeCapacity
    evaluation: CapacityEvaluation


@dataclass(frozen=True)
class CapacityGateResult:
    verdict: GateVerdict
    capacity: ComputeCapacity
    evaluation: CapacityEvaluation
    warning: str | None
    detail: str  # value-free machine code for HTTP


def ensure_acu_ledger(con: Any) -> None:
    ensure_table(con)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_compute_acu_ledger (
            investigation_id  TEXT PRIMARY KEY,
            owner_user_id     TEXT NOT NULL,
            acu_units         INTEGER NOT NULL CHECK (acu_units > 0),
            reason            TEXT NOT NULL,
            recorded_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _ensure_owner_row(con: Any, owner_user_id: str) -> ComputeCapacity:
    """Materialize default capacity so usage increments have a row to update."""
    cap = get_capacity(con, owner_user_id)
    if cap.is_default:
        return set_capacity(
            con,
            owner_user_id=owner_user_id,
            tier=cap.tier,
            monthly_compute_units=cap.monthly_compute_units,
        )
    return cap


def evaluate_with_near_limit(capacity: ComputeCapacity) -> CapacityEvaluation:
    """Extend evaluate_capacity with near-limit soft_warn semantics."""
    base = evaluate_capacity(capacity)
    if capacity.used_status != "known" or capacity.used_compute_units is None:
        return base
    if capacity.monthly_compute_units <= 0:
        return base
    ratio = capacity.used_compute_units / capacity.monthly_compute_units
    near = ratio >= NEAR_LIMIT_RATIO
    soft_over = base.soft_over or (
        capacity.enforcement in {"soft", "hard"} and near
    )
    # Preserve hard semantics from base; annotate near-limit in note.
    note = base.note
    if near and "near_limit" not in note:
        note = f"{note}|near_limit"
    return CapacityEvaluation(
        allowed=base.allowed,
        soft_over=soft_over if capacity.enforcement != "off" else False,
        would_hard_block=base.would_hard_block,
        enforcement=base.enforcement,
        used_status=base.used_status,
        note=note,
    )


def gate_investigation_start(con: Any, owner_user_id: str) -> CapacityGateResult:
    """Pre-commit gate. Hard refuse only when enforcement=hard and over limit."""
    ensure_acu_ledger(con)
    capacity = get_capacity(con, owner_user_id)
    evaluation = evaluate_with_near_limit(capacity)

    if (
        capacity.enforcement == "hard"
        and capacity.used_status == "known"
        and capacity.used_compute_units is not None
        and capacity.used_compute_units >= capacity.monthly_compute_units
    ):
        return CapacityGateResult(
            verdict="hard_refuse",
            capacity=capacity,
            evaluation=evaluation,
            warning=None,
            detail="compute_capacity_exhausted",
        )

    if capacity.enforcement in {"soft", "hard"} and evaluation.soft_over:
        used = capacity.used_compute_units
        limit = capacity.monthly_compute_units
        warn = (
            f"Antiek-hosted compute near or over monthly capacity "
            f"({used}/{limit} ACU). BYO Token spend is separate. "
            f"enforcement={capacity.enforcement}."
        )
        return CapacityGateResult(
            verdict="soft_warn",
            capacity=capacity,
            evaluation=evaluation,
            warning=warn,
            detail="compute_capacity_soft_warn",
        )

    return CapacityGateResult(
        verdict="ok",
        capacity=capacity,
        evaluation=evaluation,
        warning=None,
        detail="compute_capacity_ok",
    )


def record_investigation_start_acu(
    con: Any,
    *,
    owner_user_id: str,
    investigation_id: str,
    reason: str = "investigation_start",
    acu_units: int = ACU_PER_INVESTIGATION_START,
) -> AcuRecordResult:
    """Idempotently charge ACU for one investigation start."""
    if acu_units <= 0:
        raise ValueError("acu_units_must_be_positive")
    ensure_acu_ledger(con)
    existing = con.execute(
        "SELECT acu_units FROM owner_compute_acu_ledger WHERE investigation_id = ?",
        [investigation_id],
    ).fetchone()
    if existing is not None:
        cap = get_capacity(con, owner_user_id)
        return AcuRecordResult(
            owner_user_id=owner_user_id,
            investigation_id=investigation_id,
            acu_units=int(existing[0]),
            replayed=True,
            capacity=cap,
            evaluation=evaluate_with_near_limit(cap),
        )

    _ensure_owner_row(con, owner_user_id)
    now = _iso_now()
    con.execute(
        """
        INSERT INTO owner_compute_acu_ledger (
            investigation_id, owner_user_id, acu_units, reason, recorded_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [investigation_id, owner_user_id, acu_units, reason, now],
    )
    con.execute(
        """
        UPDATE owner_compute_capacity
        SET used_compute_units = COALESCE(used_compute_units, 0) + ?,
            used_status = 'known',
            updated_at = ?
        WHERE owner_user_id = ?
        """,
        [acu_units, now, owner_user_id],
    )
    cap = get_capacity(con, owner_user_id)
    return AcuRecordResult(
        owner_user_id=owner_user_id,
        investigation_id=investigation_id,
        acu_units=acu_units,
        replayed=False,
        capacity=cap,
        evaluation=evaluate_with_near_limit(cap),
    )



def wall_topup_ledger_id(investigation_id: str) -> str:
    """Synthetic ledger PK for completion wall top-up (idempotent)."""
    return f"{investigation_id}{WALL_TOPUP_ID_SUFFIX}"


def compute_wall_topup_acu(wall_seconds: float) -> int:
    """Map wall duration to top-up ACU units (0..WALL_TOPUP_MAX_ACU).

    Honest quantum: full 300s blocks only; no fractional ACU; hard cap 12.
    """
    if wall_seconds <= 0:
        return 0
    units = int(wall_seconds // WALL_TOPUP_QUANTUM_SECONDS)
    return min(units, WALL_TOPUP_MAX_ACU)


def _parse_ledger_ts(value: object) -> datetime | None:
    """Parse DuckDB TIMESTAMP / ISO string to aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def lookup_start_acu_row(
    con: Any, investigation_id: str
) -> tuple[str, datetime] | None:
    """Return (owner_user_id, recorded_at) for the start charge, else None."""
    ensure_acu_ledger(con)
    row = con.execute(
        """
        SELECT owner_user_id, recorded_at
        FROM owner_compute_acu_ledger
        WHERE investigation_id = ?
        """,
        [investigation_id],
    ).fetchone()
    if row is None:
        return None
    owner = str(row[0])
    started = _parse_ledger_ts(row[1])
    if started is None:
        return None
    return owner, started


def record_investigation_wall_topup_acu(
    con: Any,
    *,
    investigation_id: str,
    owner_user_id: str | None = None,
    wall_seconds: float | None = None,
    ended_at: datetime | None = None,
) -> AcuRecordResult | None:
    """Idempotently charge wall-time top-up ACU after investigation terminal.

    Returns None when there is no start row or computed top-up is 0.
    Soft/hard enforcement is *not* re-gated here — start already passed the
    gate; top-up updates ``used_compute_units`` so later starts see truth.
    """
    ensure_acu_ledger(con)
    start = lookup_start_acu_row(con, investigation_id)
    if start is None:
        return None
    start_owner, started_at = start
    owner = owner_user_id or start_owner

    if wall_seconds is None:
        end = ended_at or datetime.now(UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        wall_seconds = max(0.0, (end.astimezone(UTC) - started_at).total_seconds())

    acu_units = compute_wall_topup_acu(float(wall_seconds))
    ledger_id = wall_topup_ledger_id(investigation_id)

    existing = con.execute(
        "SELECT acu_units FROM owner_compute_acu_ledger WHERE investigation_id = ?",
        [ledger_id],
    ).fetchone()
    if existing is not None:
        cap = get_capacity(con, owner)
        return AcuRecordResult(
            owner_user_id=owner,
            investigation_id=ledger_id,
            acu_units=int(existing[0]),
            replayed=True,
            capacity=cap,
            evaluation=evaluate_with_near_limit(cap),
        )

    if acu_units <= 0:
        return None

    _ensure_owner_row(con, owner)
    now = _iso_now()
    con.execute(
        """
        INSERT INTO owner_compute_acu_ledger (
            investigation_id, owner_user_id, acu_units, reason, recorded_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [ledger_id, owner, acu_units, WALL_TOPUP_REASON, now],
    )
    con.execute(
        """
        UPDATE owner_compute_capacity
        SET used_compute_units = COALESCE(used_compute_units, 0) + ?,
            used_status = 'known',
            updated_at = ?
        WHERE owner_user_id = ?
        """,
        [acu_units, now, owner],
    )
    cap = get_capacity(con, owner)
    return AcuRecordResult(
        owner_user_id=owner,
        investigation_id=ledger_id,
        acu_units=acu_units,
        replayed=False,
        capacity=cap,
        evaluation=evaluate_with_near_limit(cap),
    )


def maybe_commit_investigation_wall_topup(
    investigation_id: str,
    *,
    db_path: str | None = None,
    owner_user_id: str | None = None,
    wall_seconds: float | None = None,
) -> int:
    """Best-effort write-lock commit for runners. Returns ACU charged (0 if none).

    Never raises — completion must not fail because metering failed. But a
    charge that is DROPPED is logged at WARNING with the investigation id
    and the cause: a silent ``return 0`` made a dropped wall-time charge
    indistinguishable from a run under the top-up floor, so the capacity
    gate then refused (or not) on an under-count it treated as known.
    """
    try:
        from runtime.db_lock import WriteLockTimeout, connect_write
        from substrate.graph import default_db_path
    except Exception as exc:
        _log.warning(
            "wall-topup DROPPED for %s: metering imports unavailable (%s)",
            investigation_id, exc,
        )
        return 0
    path = db_path or default_db_path()
    try:
        with connect_write(
            path, purpose="compute-capacity:wall-topup", timeout_s=15.0
        ) as con:
            result = record_investigation_wall_topup_acu(
                con,
                investigation_id=investigation_id,
                owner_user_id=owner_user_id,
                wall_seconds=wall_seconds,
            )
    except WriteLockTimeout as exc:
        _log.warning(
            "wall-topup DROPPED for %s: write lock not acquired within 15s (%s) "
            "— used_compute_units is now UNDER-counted for this investigation",
            investigation_id, exc,
        )
        return 0
    except Exception as exc:
        _log.warning(
            "wall-topup DROPPED for %s: %s: %s — used_compute_units is now "
            "UNDER-counted for this investigation",
            investigation_id, type(exc).__name__, exc,
        )
        return 0
    if result is None or result.replayed:
        return 0
    return int(result.acu_units)


def capacity_warning_payload(gate: CapacityGateResult) -> dict[str, Any] | None:
    if gate.verdict == "ok" or gate.warning is None:
        return None
    return {
        "code": gate.detail,
        "message": gate.warning,
        "used_compute_units": gate.capacity.used_compute_units,
        "monthly_compute_units": gate.capacity.monthly_compute_units,
        "enforcement": gate.capacity.enforcement,
        "used_status": gate.capacity.used_status,
    }


def capacity_exhausted_payload(gate: CapacityGateResult) -> dict[str, Any]:
    """Structured 429 detail for hard refuse — no fake billing; ACU only."""
    used = gate.capacity.used_compute_units
    limit = gate.capacity.monthly_compute_units
    msg = (
        f"Antiek-hosted compute at monthly capacity "
        f"({used}/{limit} ACU). New research starts are refused until "
        f"capacity resets or the monthly ACU limit is raised in Settings. "
        f"BYO Token spend is separate."
    )
    payload = {
        "code": gate.detail,
        "message": msg,
        "used_compute_units": used,
        "monthly_compute_units": limit,
        "enforcement": gate.capacity.enforcement,
        "used_status": gate.capacity.used_status,
        "retryable": False,
    }
    assert_capacity_exhausted_shape(payload)
    return payload
