"""DuckDB SoT for per-owner Antiek-hosted compute capacity.

Table ``owner_compute_capacity`` is the durable preference + soft quota.
Used units are written by ``acu_meter.record_investigation_start_acu``
(1 ACU per investigation start). Until the first charge, ``used_status``
stays ``unmetered``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

CapacityTier = Literal["starter", "standard", "power", "custom"]
UsedStatus = Literal["unmetered", "known"]
EnforcementMode = Literal["off", "soft", "hard"]

CAPACITY_TIERS: tuple[CapacityTier, ...] = (
    "starter",
    "standard",
    "power",
    "custom",
)

# Abstract Agent Compute Units (ACU) per month — not USD. Pricing maps later.
_TIER_DEFAULT_UNITS: dict[str, int] = {
    "starter": 100,
    "standard": 500,
    "power": 2000,
}

_MIN_UNITS = 0
_MAX_UNITS = 50_000
_DEFAULT_TIER: CapacityTier = "standard"
_ENFORCEMENT_ENV = "ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT"


@dataclass(frozen=True)
class ComputeCapacity:
    owner_user_id: str
    tier: CapacityTier
    monthly_compute_units: int
    used_compute_units: int | None
    used_status: UsedStatus
    enforcement: EnforcementMode
    updated_at: str | None
    is_default: bool


@dataclass(frozen=True)
class CapacityEvaluation:
    """Soft/hard gate snapshot — does not invent usage when unmetered."""

    allowed: bool
    soft_over: bool
    would_hard_block: bool
    enforcement: EnforcementMode
    used_status: UsedStatus
    note: str


def tier_default_units(tier: str) -> int | None:
    return _TIER_DEFAULT_UNITS.get(tier)


def enforcement_from_env(env: dict[str, str] | None = None) -> EnforcementMode:
    source = env if env is not None else os.environ
    raw = (source.get(_ENFORCEMENT_ENV) or "off").strip().lower()
    if raw in {"off", "soft", "hard"}:
        return raw  # type: ignore[return-value]
    return "off"


def ensure_table(con: Any) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_compute_capacity (
            owner_user_id          TEXT PRIMARY KEY,
            tier                   TEXT NOT NULL
                CHECK (tier IN ('starter', 'standard', 'power', 'custom')),
            monthly_compute_units  INTEGER NOT NULL
                CHECK (monthly_compute_units >= 0
                       AND monthly_compute_units <= 50000),
            used_compute_units     INTEGER
                CHECK (used_compute_units IS NULL
                       OR used_compute_units >= 0),
            used_status            TEXT NOT NULL DEFAULT 'unmetered'
                CHECK (used_status IN ('unmetered', 'known')),
            updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _row_to_capacity(
    row: tuple[Any, ...],
    *,
    enforcement: EnforcementMode,
    is_default: bool = False,
) -> ComputeCapacity:
    used_status: UsedStatus = str(row[4])  # type: ignore[assignment]
    used_raw = row[3]
    used: int | None = None if used_status == "unmetered" else int(used_raw) if used_raw is not None else 0
    updated = row[5]
    updated_s: str | None
    if updated is None:
        updated_s = None
    elif hasattr(updated, "isoformat"):
        updated_s = str(updated.isoformat())
    else:
        updated_s = str(updated)
    return ComputeCapacity(
        owner_user_id=str(row[0]),
        tier=str(row[1]),  # type: ignore[arg-type]
        monthly_compute_units=int(row[2]),
        used_compute_units=used,
        used_status=used_status,
        enforcement=enforcement,
        updated_at=updated_s,
        is_default=is_default,
    )


def _default_capacity(owner_user_id: str, enforcement: EnforcementMode) -> ComputeCapacity:
    return ComputeCapacity(
        owner_user_id=owner_user_id,
        tier=_DEFAULT_TIER,
        monthly_compute_units=_TIER_DEFAULT_UNITS[_DEFAULT_TIER],
        used_compute_units=None,
        used_status="unmetered",
        enforcement=enforcement,
        updated_at=None,
        is_default=True,
    )


def _table_exists(con: Any) -> bool:
    row = con.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'owner_compute_capacity'
        """
    ).fetchone()
    return row is not None


def get_capacity(con: Any, owner_user_id: str) -> ComputeCapacity:
    """Read capacity. Never CREATE on a read-only connection."""
    enforcement = enforcement_from_env()
    if not _table_exists(con):
        return _default_capacity(owner_user_id, enforcement)
    row = con.execute(
        """
        SELECT owner_user_id, tier, monthly_compute_units,
               used_compute_units, used_status, updated_at
        FROM owner_compute_capacity WHERE owner_user_id = ?
        """,
        [owner_user_id],
    ).fetchone()
    if row is None:
        return _default_capacity(owner_user_id, enforcement)
    return _row_to_capacity(row, enforcement=enforcement, is_default=False)


def set_capacity(
    con: Any,
    *,
    owner_user_id: str,
    tier: str,
    monthly_compute_units: int | None = None,
) -> ComputeCapacity:
    """Upsert owner preference. Preset tiers snap units; custom requires units."""
    ensure_table(con)
    if tier not in CAPACITY_TIERS:
        raise ValueError("invalid_tier")
    if tier == "custom":
        if monthly_compute_units is None:
            raise ValueError("custom_requires_units")
        units = int(monthly_compute_units)
    else:
        default = _TIER_DEFAULT_UNITS[tier]
        units = int(monthly_compute_units) if monthly_compute_units is not None else default
        # If caller overrides units off the preset, coerce to custom.
        if units != default:
            tier = "custom"
    if units < _MIN_UNITS or units > _MAX_UNITS:
        raise ValueError("units_out_of_range")

    now = _iso_now()
    # Preserve known meter if present; never invent usage on write.
    existing = con.execute(
        "SELECT used_compute_units, used_status FROM owner_compute_capacity "
        "WHERE owner_user_id = ?",
        [owner_user_id],
    ).fetchone()
    if existing is None:
        used_units, used_status = None, "unmetered"
    else:
        used_units, used_status = existing[0], existing[1]

    con.execute(
        """
        INSERT INTO owner_compute_capacity (
            owner_user_id, tier, monthly_compute_units,
            used_compute_units, used_status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (owner_user_id) DO UPDATE SET
            tier = excluded.tier,
            monthly_compute_units = excluded.monthly_compute_units,
            updated_at = excluded.updated_at
        """,
        [owner_user_id, tier, units, used_units, used_status, now],
    )
    return get_capacity(con, owner_user_id)


def evaluate_capacity(capacity: ComputeCapacity) -> CapacityEvaluation:
    """Flag-gated soft/hard check. Unmetered usage never soft-overs or blocks."""
    enforcement = capacity.enforcement
    if capacity.used_status != "known" or capacity.used_compute_units is None:
        return CapacityEvaluation(
            allowed=True,
            soft_over=False,
            would_hard_block=False,
            enforcement=enforcement,
            used_status=capacity.used_status,
            note="used_unmetered_no_fake_billing",
        )
    over = capacity.used_compute_units >= capacity.monthly_compute_units
    if enforcement == "off":
        return CapacityEvaluation(
            allowed=True,
            soft_over=False,
            would_hard_block=False,
            enforcement=enforcement,
            used_status="known",
            note="enforcement_off",
        )
    if enforcement == "soft":
        return CapacityEvaluation(
            allowed=True,
            soft_over=over,
            would_hard_block=False,
            enforcement=enforcement,
            used_status="known",
            note="soft_warn_only" if over else "within_capacity",
        )
    # hard — research-start gate refuses when over (see gate_investigation_start)
    return CapacityEvaluation(
        allowed=not over,
        soft_over=over,
        would_hard_block=over,
        enforcement=enforcement,
        used_status="known",
        note="hard_would_block" if over else "within_capacity",
    )
