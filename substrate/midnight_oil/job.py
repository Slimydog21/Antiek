"""Midnight Oil job schema: create → recommend ceiling → approve."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, Protocol, cast, runtime_checkable

from substrate.dispatch.research_tier import (
    DEFAULT_RESEARCH_TIER,
    normalize_research_tier,
)

from .ceiling import ModelPricing, recommend_price_ceiling

JobStatus = Literal[
    "draft",
    "awaiting_approval",
    "approved",
    "running",
    "complete",
    "timed_out",
    "budget_halted",
    "failed",
]
_VALID_JOB_STATUSES = frozenset(
    {
        "draft",
        "awaiting_approval",
        "approved",
        "running",
        "complete",
        "timed_out",
        "budget_halted",
        "failed",
    }
)

OperationState = Literal[
    "awaiting_approval",
    "approved",
    "dispatch_claimed",
    "dispatch_started",
    "dispatch_finished",
    "failed_closed",
]

_VALID_OPERATION_STATES = frozenset(
    {
        "awaiting_approval",
        "approved",
        "dispatch_claimed",
        "dispatch_started",
        "dispatch_finished",
        "failed_closed",
    }
)
_MAX_SQLITE_INTEGER = 2**63 - 1
_LEGAL_OPERATION_TRANSITIONS: dict[OperationState, frozenset[OperationState]] = {
    "awaiting_approval": frozenset({"approved", "failed_closed"}),
    "approved": frozenset({"dispatch_claimed", "failed_closed"}),
    "dispatch_claimed": frozenset({"dispatch_started", "failed_closed"}),
    "dispatch_started": frozenset({"dispatch_finished", "failed_closed"}),
    "dispatch_finished": frozenset(),
    "failed_closed": frozenset(),
}


def _validate_operation_state(value: object) -> OperationState:
    if value not in _VALID_OPERATION_STATES:
        raise ValueError(f"unknown Midnight Oil authority state: {value!r}")
    return cast(OperationState, value)


def _validate_job_status(value: object) -> JobStatus:
    if value not in _VALID_JOB_STATUSES:
        raise ValueError(f"unknown Midnight Oil job status: {value!r}")
    return cast(JobStatus, value)


def _validate_identifier(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validate_timestamp(value: object | None, *, field_name: str) -> int | None:
    return _validate_integer(value, field_name=field_name, allow_none=True)


def _validate_integer(value: object | None, *, field_name: str, allow_none: bool) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} is required")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a non-negative integer")
    if value < 0 or value > _MAX_SQLITE_INTEGER:
        raise ValueError(f"{field_name} is outside the supported integer range")
    return value


def _validate_cents(
    value: object | None,
    *,
    field_name: str,
    allow_none: bool,
) -> int | None:
    result = _validate_integer(value, field_name=field_name, allow_none=allow_none)
    if result is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{field_name} must be an integer number of cents")
    return result


def _legacy_usd_to_cents_floor(value: float, *, field_name: str) -> int:
    try:
        cents = (Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_FLOOR)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite USD amount") from exc
    return _validate_cents(int(cents), field_name=field_name, allow_none=False) or 0


@dataclass(frozen=True)
class MidnightOilJobAuthority:
    owner_user_id: str
    state_version: int = 0
    approved_ceiling_cents: int | None = None
    consent_granted_by_user_id: str | None = None
    consent_recorded_at_ms: int | None = None
    consent_note: str = ""
    operation_state: OperationState = "awaiting_approval"
    operation_id: str | None = None
    dispatch_claimed_at_ms: int | None = None
    dispatch_started_at_ms: int | None = None
    dispatch_completed_at_ms: int | None = None


def _validate_authority(authority: MidnightOilJobAuthority) -> None:
    _validate_identifier(authority.owner_user_id, field_name="owner_user_id")
    _validate_integer(authority.state_version, field_name="state_version", allow_none=False)
    _validate_cents(
        authority.approved_ceiling_cents, field_name="approved_ceiling_cents", allow_none=True
    )
    state = _validate_operation_state(authority.operation_state)
    if authority.operation_id is not None:
        _validate_identifier(authority.operation_id, field_name="operation_id")
    timestamps = (
        _validate_timestamp(authority.dispatch_claimed_at_ms, field_name="dispatch_claimed_at_ms"),
        _validate_timestamp(authority.dispatch_started_at_ms, field_name="dispatch_started_at_ms"),
        _validate_timestamp(
            authority.dispatch_completed_at_ms, field_name="dispatch_completed_at_ms"
        ),
    )
    consent_at = _validate_timestamp(
        authority.consent_recorded_at_ms, field_name="consent_recorded_at_ms"
    )
    if authority.consent_granted_by_user_id is not None:
        _validate_identifier(
            authority.consent_granted_by_user_id, field_name="consent_granted_by_user_id"
        )
    if (authority.consent_granted_by_user_id is None) != (consent_at is None):
        raise ValueError("consent identity and timestamp must be recorded together")
    has_dispatch_history = authority.operation_id is not None or any(
        timestamp is not None for timestamp in timestamps
    )
    requires_approval = state not in {"awaiting_approval", "failed_closed"} or (
        state == "failed_closed" and has_dispatch_history
    )
    if requires_approval:
        if authority.approved_ceiling_cents is None or authority.approved_ceiling_cents <= 0:
            raise ValueError(f"{state} requires a positive approved ceiling")
        if authority.consent_granted_by_user_id is None or consent_at is None:
            raise ValueError(f"{state} requires durable consent identity and timestamp")
    claimed, started, completed = timestamps
    if started is not None and claimed is None:
        raise ValueError("dispatch start requires a claim timestamp")
    if completed is not None and started is None:
        raise ValueError("dispatch completion requires a start timestamp")
    if claimed is not None and started is not None and claimed > started:
        raise ValueError("dispatch timestamps are out of order")
    if started is not None and completed is not None and started > completed:
        raise ValueError("dispatch timestamps are out of order")
    required_count = {
        "awaiting_approval": 0,
        "approved": 0,
        "dispatch_claimed": 1,
        "dispatch_started": 2,
        "dispatch_finished": 3,
    }.get(state)
    if required_count is not None:
        operation_required = state in {
            "dispatch_claimed",
            "dispatch_started",
            "dispatch_finished",
        }
        operation_forbidden = state == "awaiting_approval"
        if operation_required and authority.operation_id is None:
            raise ValueError(f"operation identity is inconsistent with {state}")
        if operation_forbidden and authority.operation_id is not None:
            raise ValueError(f"operation identity is inconsistent with {state}")
        if sum(value is not None for value in timestamps) != required_count:
            raise ValueError(f"dispatch timestamps are inconsistent with {state}")
    elif any(value is not None for value in timestamps) and authority.operation_id is None:
        raise ValueError("dispatch timestamps require an operation identity")


def _validate_authority_transition(
    current: MidnightOilJobAuthority, proposed: MidnightOilJobAuthority
) -> None:
    _validate_authority(proposed)
    if proposed.operation_state not in _LEGAL_OPERATION_TRANSITIONS[current.operation_state]:
        raise ValueError(
            f"illegal authority transition: {current.operation_state} -> {proposed.operation_state}"
        )
    if current.operation_id is not None and proposed.operation_id != current.operation_id:
        raise ValueError("an established operation identity cannot be changed or cleared")
    if current.operation_state != "awaiting_approval":
        current_approval = (
            current.approved_ceiling_cents,
            current.consent_granted_by_user_id,
            current.consent_recorded_at_ms,
            current.consent_note,
        )
        proposed_approval = (
            proposed.approved_ceiling_cents,
            proposed.consent_granted_by_user_id,
            proposed.consent_recorded_at_ms,
            proposed.consent_note,
        )
        if proposed_approval != current_approval:
            raise ValueError("approved ceiling and consent are immutable after approval")


@dataclass(frozen=True)
class MidnightOilJob:
    job_id: str
    goals: tuple[str, ...]
    duration_minutes: int
    model_id: str | None
    recommended_price_ceiling_usd: float
    status: JobStatus
    approved_ceiling_usd: float | None = None
    spent_usd: float = 0.0
    asset_id: str | None = None
    spawn_ids: tuple[str, ...] = ()
    started_at_ms: int | None = None
    elapsed_ms: int = 0
    force_below_recommended: bool = False
    notes: str = ""
    # Residual (gs): curated research tier for autonomous runs (fast|deep|wrestle).
    research_tier: str = DEFAULT_RESEARCH_TIER
    # Residual (adb): fan-out depth used for recommended ceiling (parity formula).
    fanout_depth: int = 3
    completed_step_keys: tuple[str, ...] = ()
    returned_step_keys: tuple[str, ...] = ()
    authority: MidnightOilJobAuthority | None = None


@runtime_checkable
class JobStore(Protocol):
    def put_job(self, job: dict[str, Any]) -> None: ...
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    def budget_db_path(self) -> str: ...


@runtime_checkable
class OwnerScopedJobStore(Protocol):
    def put_job_for_owner(self, owner_user_id: str, job: MidnightOilJob) -> MidnightOilJob: ...
    def get_job_for_owner(
        self,
        job_id: str,
        owner_user_id: str,
    ) -> MidnightOilJob | None: ...


@dataclass
class InMemoryJobStore:
    _jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _budget_dir: TemporaryDirectory[str] = field(default_factory=TemporaryDirectory, repr=False)

    def put_job(self, job: dict[str, Any]) -> None:
        self._jobs[job["job_id"]] = dict(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._jobs.get(job_id)
        return dict(row) if row is not None else None

    def budget_db_path(self) -> str:
        """Return the store-scoped durable ledger used by its worker jobs."""
        return str(Path(self._budget_dir.name) / "midnight-oil-budget.duckdb")


def _job_to_row(job: MidnightOilJob) -> dict[str, Any]:
    authority = job.authority
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "status": job.status,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "spent_usd": job.spent_usd,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "started_at_ms": job.started_at_ms,
        "elapsed_ms": job.elapsed_ms,
        "force_below_recommended": job.force_below_recommended,
        "notes": job.notes,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "completed_step_keys": list(job.completed_step_keys),
        "returned_step_keys": list(job.returned_step_keys),
        "owner_user_id": None if authority is None else authority.owner_user_id,
        "state_version": None if authority is None else authority.state_version,
        "approved_ceiling_cents": (None if authority is None else authority.approved_ceiling_cents),
        "consent_granted_by_user_id": (
            None if authority is None else authority.consent_granted_by_user_id
        ),
        "consent_recorded_at_ms": (None if authority is None else authority.consent_recorded_at_ms),
        "consent_note": None if authority is None else authority.consent_note,
        "operation_state": None if authority is None else authority.operation_state,
        "operation_id": None if authority is None else authority.operation_id,
        "dispatch_claimed_at_ms": (None if authority is None else authority.dispatch_claimed_at_ms),
        "dispatch_started_at_ms": (None if authority is None else authority.dispatch_started_at_ms),
        "dispatch_completed_at_ms": (
            None if authority is None else authority.dispatch_completed_at_ms
        ),
    }


def _job_from_row(row: dict[str, Any]) -> MidnightOilJob:
    fanout = int(row.get("fanout_depth") or 3)
    if fanout <= 0:
        fanout = 3
    authority: MidnightOilJobAuthority | None = None
    owner_user_id = row.get("owner_user_id")
    if owner_user_id is not None:
        state_version = _validate_cents(
            row.get("state_version"),
            field_name="state_version",
            allow_none=False,
        )
        operation_state = _validate_operation_state(
            row.get("operation_state") or "awaiting_approval"
        )
        authority = MidnightOilJobAuthority(
            owner_user_id=owner_user_id,
            state_version=state_version or 0,
            approved_ceiling_cents=_validate_cents(
                row.get("approved_ceiling_cents"),
                field_name="approved_ceiling_cents",
                allow_none=True,
            ),
            consent_granted_by_user_id=row.get("consent_granted_by_user_id"),
            consent_recorded_at_ms=row.get("consent_recorded_at_ms"),
            consent_note=str(row.get("consent_note") or ""),
            operation_state=operation_state,
            operation_id=row.get("operation_id"),
            dispatch_claimed_at_ms=row.get("dispatch_claimed_at_ms"),
            dispatch_started_at_ms=row.get("dispatch_started_at_ms"),
            dispatch_completed_at_ms=row.get("dispatch_completed_at_ms"),
        )
        _validate_authority(authority)
    status = _validate_job_status(row["status"])
    return MidnightOilJob(
        job_id=row["job_id"],
        goals=tuple(row.get("goals") or ()),
        duration_minutes=int(row["duration_minutes"]),
        model_id=row.get("model_id"),
        recommended_price_ceiling_usd=float(row["recommended_price_ceiling_usd"]),
        status=status,
        approved_ceiling_usd=(
            None if row.get("approved_ceiling_usd") is None else float(row["approved_ceiling_usd"])
        ),
        spent_usd=float(row.get("spent_usd") or 0.0),
        asset_id=row.get("asset_id"),
        spawn_ids=tuple(row.get("spawn_ids") or ()),
        started_at_ms=row.get("started_at_ms"),
        elapsed_ms=int(row.get("elapsed_ms") or 0),
        force_below_recommended=bool(row.get("force_below_recommended") or False),
        notes=str(row.get("notes") or ""),
        research_tier=normalize_research_tier(row.get("research_tier")),
        fanout_depth=fanout,
        completed_step_keys=tuple(row.get("completed_step_keys") or ()),
        returned_step_keys=tuple(row.get("returned_step_keys") or ()),
        authority=authority,
    )


def create_job(
    goals: list[str] | tuple[str, ...],
    duration_minutes: int,
    *,
    store: JobStore,
    model_id: str | None = None,
    fanout_depth: int = 3,
    pricing: ModelPricing | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
    research_tier: str | None = None,
    owner_user_id: str | None = None,
) -> MidnightOilJob:
    """Create a draft Midnight Oil job with a recommended price ceiling.

    Does **not** start work — operator must ``approve_job`` first.
    """
    cleaned = tuple(g.strip() for g in goals if g and str(g).strip())
    if not cleaned:
        raise ValueError("at least one non-empty goal is required")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")

    jid = job_id or f"moil_{uuid.uuid4().hex[:16]}"
    tier = normalize_research_tier(research_tier)
    # Residual (jl): ceiling recommendation scales with research_tier.
    ceiling = recommend_price_ceiling(
        duration_minutes,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        research_tier=tier,
    )
    job = MidnightOilJob(
        job_id=jid,
        goals=cleaned,
        duration_minutes=duration_minutes,
        model_id=model_id,
        recommended_price_ceiling_usd=ceiling,
        status="awaiting_approval",
        asset_id=asset_id or f"moil_asset_{jid.removeprefix('moil_')}",
        research_tier=tier,
        # Residual (adb): persist fanout used for ceiling so API/UI formula match.
        fanout_depth=int(fanout_depth) if int(fanout_depth) > 0 else 3,
        authority=(
            None if owner_user_id is None else MidnightOilJobAuthority(owner_user_id=owner_user_id)
        ),
    )
    store.put_job(_job_to_row(job))
    return job


def approve_job(
    job_id: str,
    ceiling_usd: float,
    *,
    store: JobStore,
    force_below: bool = False,
) -> MidnightOilJob:
    """Explicitly approve a price ceiling before the worker may run.

    Requires ``ceiling_usd >= recommended`` unless ``force_below`` is True
    (operator override with a recorded warning note).
    """
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    if job.status not in ("awaiting_approval", "draft"):
        raise ValueError(f"job {job_id} status is {job.status!r}; cannot approve")
    if ceiling_usd <= 0:
        raise ValueError("ceiling_usd must be positive")
    if ceiling_usd < job.recommended_price_ceiling_usd and not force_below:
        raise ValueError(
            f"ceiling_usd {ceiling_usd} is below recommended "
            f"{job.recommended_price_ceiling_usd}; pass force_below=True to override"
        )
    notes = job.notes
    if ceiling_usd < job.recommended_price_ceiling_usd and force_below:
        notes = (notes + " | " if notes else "") + (
            f"force_below: approved {ceiling_usd} < recommended {job.recommended_price_ceiling_usd}"
        )
    updated = replace(
        job,
        status="approved",
        approved_ceiling_usd=float(ceiling_usd),
        force_below_recommended=bool(
            force_below and ceiling_usd < job.recommended_price_ceiling_usd
        ),
        notes=notes,
        authority=(
            None
            if job.authority is None
            else replace(
                job.authority,
                approved_ceiling_cents=_legacy_usd_to_cents_floor(
                    ceiling_usd,
                    field_name="ceiling_usd",
                ),
                operation_state="approved",
            )
        ),
    )
    store.put_job(_job_to_row(updated))
    return updated


def get_job(job_id: str, *, store: JobStore) -> MidnightOilJob | None:
    row = store.get_job(job_id)
    return _job_from_row(row) if row else None


def put_job_state(job: MidnightOilJob, *, store: JobStore) -> MidnightOilJob:
    store.put_job(_job_to_row(job))
    return job
