"""ACU metering for Antiek-hosted agent compute.

Doctrine (docs/decisions/byot-capacity-slider-2026-09-18.md + this module):
BYO Token spend stays on the usage ledger. ACU meters *Antiek-managed*
orchestration / retrieval / event-log CPU committed when an investigation
starts — not LLM cents, not wall-clock dollars.

Heuristic (honest, deliberate — not fake pricing):

    1 ACU = one investigation start
            (``POST /investigations`` or ``POST /books/.../spin-research``)

Rationale: at start we commit host CPU (orchestrator spawn, DuckDB
contention, retrieval, event append). Dispatch ``latency_ms`` and role-call
counts are BYOT-adjacent and incomplete at the pre-commit gate; charging
flat 1 ACU at start makes soft-warn / hard-refuse decidable *before* work
begins. Refinement (wall-time top-up on completion) is a later PR.

Idempotency: ``owner_compute_acu_ledger`` keys on ``investigation_id`` so
exact launch replays do not double-charge.
"""

from __future__ import annotations

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

ACU_PER_INVESTIGATION_START = 1
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


def capacity_warning_payload(gate: CapacityGateResult) -> dict[str, object] | None:
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
