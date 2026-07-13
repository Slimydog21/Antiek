"""Authenticated, owner-bound Midnight Oil HTTP surface.

The durable owner store is the authorization boundary.  The legacy job store
remains an execution/detail substrate until the worker migration, but is never
queried until ownership has been established.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from substrate.midnight_oil import (
    LiveExecutionPlan,
    MidnightOilExecutionReceipt,
    MidnightOilExecutionRequest,
    MidnightOilPreflight,
    MidnightOilRequest,
    ResearchAcceptancePolicy,
    create_with_recommended_ceiling,
    deposit_job_results,
    execute_midnight_oil,
    get_job,
    job_summary_html,
    preflight_midnight_oil,
    product_result_html,
    research_acceptance_policy_from_payload,
)
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.job import InMemoryJobStore, JobStore, MidnightOilJob
from substrate.midnight_oil.job_store import (
    DurableOwnerJobStore,
    OperationState,
    OwnerJob,
    OwnerJobStore,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue, OperationQueue
from substrate.midnight_oil.spend_consent import (
    MAX_CEILING_CENTS,
    ConsentReceipt,
    ConsentRejected,
    ConsentRejection,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

midnight_oil_router = APIRouter(prefix="/midnight-oil", tags=["midnight-oil"])
midnight_oil_preflight_router = APIRouter(prefix="/research/midnight-oil", tags=["deep-research"])
_DEPENDENCIES = "midnight_oil_dependencies"
CONSENT_TTL_MS = 15 * 60 * 1000


@midnight_oil_preflight_router.post("/preflight", response_model=MidnightOilPreflight)
def post_midnight_oil_preflight(req: MidnightOilRequest) -> MidnightOilPreflight:
    """Plan the approved envelope without reserving, dispatching, or retrieving."""
    return preflight_midnight_oil(req)


@midnight_oil_preflight_router.post("/execute", response_model=MidnightOilExecutionReceipt)
def post_midnight_oil_execute(
    req: MidnightOilExecutionRequest,
) -> MidnightOilExecutionReceipt:
    """Run the permanent, networkless synthetic oracle.

    Live mode remains unreachable until the operator-gated SPR-06 wiring.
    """
    return execute_midnight_oil(req)


def _system_clock_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class MidnightOilDependencies:
    owner_jobs: OwnerJobStore
    jobs: JobStore
    consents: SpendConsentStore
    active_key_id: str
    signing_key: bytes
    verification_keys: Mapping[str, bytes]
    operation_queue: OperationQueue | None = None
    live_plan_resolver: Callable[[Any], LiveExecutionPlan] | None = None
    clock_ms: Callable[[], int] = _system_clock_ms
    random_token: Callable[[int], str] = secrets.token_urlsafe
    test_mode: bool = False

    def __post_init__(self) -> None:
        if (
            not self.active_key_id
            or self.active_key_id != self.active_key_id.strip()
            or len(self.active_key_id) > 128
        ):
            raise ValueError("the active consent key id must be canonical")
        if type(self.signing_key) is not bytes or len(self.signing_key) < 32:
            raise ValueError("a 256-bit consent signing key is required")
        for key_id, key in self.verification_keys.items():
            if (
                type(key_id) is not str
                or not key_id
                or key_id != key_id.strip()
                or len(key_id) > 128
            ):
                raise ValueError("verification key ids must be canonical")
            if type(key) is not bytes or len(key) < 32:
                raise ValueError("verification keys must be at least 256 bits")
        if self.verification_keys.get(self.active_key_id) != self.signing_key:
            raise ValueError("the active signing key must be in the verification keyring")
        if not self.test_mode:
            if (
                type(self.owner_jobs) is not DurableOwnerJobStore
                or type(self.jobs) is not DurableJobStore
                or type(self.consents) is not SpendConsentStore
                or type(self.operation_queue) is not DurableOperationQueue
            ):
                raise ValueError("production Midnight Oil requires durable stores and queue")
            if self.clock_ms is not _system_clock_ms:
                raise ValueError("production Midnight Oil requires the system clock")
            if self.random_token is not secrets.token_urlsafe:
                raise ValueError("production Midnight Oil requires secrets.token_urlsafe")


def reset_midnight_oil_store(store: JobStore | None = None) -> None:
    """Removed insecure compatibility hook.

    Tests must pass an explicit :class:`MidnightOilDependencies` bundle to
    ``register_midnight_oil_routes``.  Production must do the same.
    """
    del store
    raise RuntimeError("Midnight Oil dependencies must be explicitly injected")


def _deps(request: Request) -> MidnightOilDependencies:
    value = getattr(request.app.state, _DEPENDENCIES, None)
    if not isinstance(value, MidnightOilDependencies):
        raise RuntimeError("Midnight Oil durable dependencies are not configured")
    return value


def _owner(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=401, detail="authentication required")
    return value.strip()


def _owned(request: Request, job_id: str) -> tuple[MidnightOilDependencies, OwnerJob]:
    deps = _deps(request)
    job = deps.owner_jobs.get_job(owner_user_id=_owner(request), job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return deps, job


class CreateJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goals: list[StrictStr] = Field(min_length=1, max_length=64)
    duration_minutes: StrictInt = Field(ge=1, le=10_080)
    model_id: StrictStr | None = Field(default=None, max_length=256)
    fanout_depth: StrictInt = Field(default=3, ge=1, le=64)
    research_tier: StrictStr | None = Field(default=None, max_length=64)
    live: StrictBool = False

    @field_validator("goals")
    @classmethod
    def validate_goals(cls, goals: list[str]) -> list[str]:
        if any(not goal.strip() or len(goal) > 4096 for goal in goals):
            raise ValueError("goals must be non-empty and at most 4096 characters")
        if sum(len(goal) for goal in goals) > 65_536:
            raise ValueError("combined goals are too large")
        return goals


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ceiling_cents: StrictInt | None = Field(default=None, ge=1, le=MAX_CEILING_CENTS)
    use_recommended: StrictBool = False
    force_below: StrictBool = False


class LegacyApproveBody(BaseModel):
    """Identifier-only tombstone; float approval authority is intentionally gone."""

    model_config = ConfigDict(extra="forbid")
    job_id: str


class DepositBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    draft_combined: bool = True
    record_progress: bool = True
    mark_complete: bool = True
    include_progress_html: bool = True


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: StrictStr = Field(min_length=1, max_length=256)
    max_steps: StrictInt | None = Field(default=None, ge=1, le=100_000)
    spent_per_goal: float = 0.05  # legacy display input; never queued or authoritative
    auto_deposit: StrictBool = False
    draft_combined: StrictBool = True
    force_offline: StrictBool = False


def _owner_payload(job: Any, *, live_plan: LiveExecutionPlan | None = None) -> dict[str, object]:
    recommended_cents = int(
        (Decimal(str(job.recommended_price_ceiling_usd)) * 100).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    return {
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "asset_id": job.asset_id,
        "force_below_recommended": False,
        "recommended_ceiling_cents": recommended_cents,
        "display_usd": job.recommended_price_ceiling_usd,
        "live_plan_hash": None if live_plan is None else live_plan.plan_hash,
        "live_allowed_routes": ([] if live_plan is None else list(live_plan.allowed_routes)),
        "live_projected_max_cents": (None if live_plan is None else live_plan.projected_max_cents),
        "live_source_policy": ([] if live_plan is None else list(live_plan.source_policy)),
        "live_dispatch_config_hash": (
            None if live_plan is None else live_plan.dispatch_config_hash
        ),
        "live_max_input_bytes": (None if live_plan is None else live_plan.max_input_bytes),
        "acceptance_policy_version": ResearchAcceptancePolicy().policy_version,
    }


@midnight_oil_router.post("/create")
def post_create(request: Request, body: CreateJobBody) -> dict[str, Any]:
    deps = _deps(request)
    owner = _owner(request)
    try:
        job_id = deps.random_token(20)
        asset_id = deps.random_token(28)
        if (
            type(job_id) is not str
            or not 8 <= len(job_id) <= 512
            or type(asset_id) is not str
            or not 8 <= len(asset_id) <= 512
            or job_id == asset_id
        ):
            raise RuntimeError("invalid identifier source")
        staging = InMemoryJobStore()
        result = create_with_recommended_ceiling(
            body.goals,
            body.duration_minutes,
            store=staging,
            model_id=body.model_id,
            fanout_depth=body.fanout_depth,
            job_id=job_id,
            asset_id=asset_id,
            research_tier=body.research_tier,
        )
        if body.live:
            if deps.live_plan_resolver is None:
                raise RuntimeError("live execution plan resolver is unavailable")
            live_plan = deps.live_plan_resolver(result.job)
            if not isinstance(live_plan, LiveExecutionPlan):
                raise RuntimeError("live execution plan resolver returned invalid data")
        else:
            live_plan = None
        deps.owner_jobs.put_job(
            OwnerJob(
                owner_user_id=owner,
                job_id=result.job.job_id,
                state_version=0,
                approved_ceiling_cents=None,
                consent_receipt_id=None,
                consent_config_hash=None,
                consent_issued_at_ms=None,
                consent_expires_at_ms=None,
                consent_claimed_at_ms=None,
                operation_id=None,
                operation_state=OperationState.NONE,
                dispatch_started_at_ms=None,
                dispatched_at_ms=None,
                completed_at_ms=None,
                payload=_owner_payload(result.job, live_plan=live_plan),
            )
        )
        legacy_row = staging.get_job(result.job.job_id)
        if legacy_row is None:
            raise RuntimeError("staged Midnight Oil job disappeared")
        try:
            deps.jobs.put_job(legacy_row)
        except Exception:
            # A write may commit and still raise. Delete authority only after a
            # successful read proves the detail row was not persisted.
            try:
                persisted = deps.jobs.get_job(result.job.job_id)
                read_confirmed = True
            except Exception:
                persisted = None
                read_confirmed = False
            if read_confirmed and persisted is None:
                deps.owner_jobs.delete_uninitialized_job(
                    owner_user_id=owner, job_id=result.job.job_id
                )
            raise HTTPException(status_code=503, detail="job persistence unavailable") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError:
        raise HTTPException(status_code=503, detail="job creation unavailable") from None
    out = result.to_dict()
    out["html"] = product_result_html(result)
    return out


def _config(row: OwnerJob) -> JobConsentConfig:
    payload = row.payload
    goals = payload["goals"]
    duration = payload["duration_minutes"]
    fanout = payload["fanout_depth"]
    if (
        not isinstance(goals, list)
        or not 1 <= len(goals) <= 64
        or any(type(goal) is not str or not goal.strip() or len(goal) > 4096 for goal in goals)
        or sum(len(goal) for goal in goals) > 65_536
    ):
        raise ValueError("stored goals are invalid")
    if (
        type(duration) is not int
        or not 1 <= duration <= 10_080
        or type(fanout) is not int
        or not 1 <= fanout <= 64
    ):
        raise ValueError("stored numeric configuration is invalid")
    model_id = payload.get("model_id")
    tier = payload.get("research_tier")
    asset_id = payload.get("asset_id")
    if model_id is not None and (type(model_id) is not str or len(model_id) > 256):
        raise ValueError("stored model is invalid")
    if type(tier) is not str or not tier or len(tier) > 64:
        raise ValueError("stored research tier is invalid")
    if type(asset_id) is not str or not asset_id or len(asset_id) > 256:
        raise ValueError("stored asset is invalid")
    live_plan_hash = payload.get("live_plan_hash")
    if live_plan_hash is None:
        live_plan = None
    else:
        live_plan = LiveExecutionPlan.from_payload(
            {
                "plan_hash": live_plan_hash,
                "allowed_routes": payload.get("live_allowed_routes"),
                "projected_max_cents": payload.get("live_projected_max_cents"),
                "source_policy": payload.get("live_source_policy"),
                "dispatch_config_hash": payload.get("live_dispatch_config_hash"),
                "max_input_bytes": payload.get("live_max_input_bytes"),
            }
        )
    return JobConsentConfig(
        job_id=row.job_id,
        goals=tuple(goals),
        duration_minutes=duration,
        model_id=model_id,
        research_tier=tier,
        fanout_depth=fanout,
        asset_id=asset_id,
        live_execution_plan_hash=(None if live_plan is None else live_plan.plan_hash),
        acceptance_policy=research_acceptance_policy_from_payload(
            None
            if payload.get("acceptance_policy_version") is None
            else {"policy_version": payload["acceptance_policy_version"]}
        ),
    )


def _recommended_cents(row: OwnerJob) -> int:
    value = row.payload.get("recommended_ceiling_cents")
    if type(value) is not int or not 1 <= value <= MAX_CEILING_CENTS:
        raise ValueError("stored recommended ceiling is invalid")
    return value


def _legacy_matches_authority(legacy: MidnightOilJob, config: JobConsentConfig) -> bool:
    """Require the ownerless detail projection to match signed authority exactly."""
    return (
        legacy.job_id == config.job_id
        and legacy.goals == config.goals
        and legacy.duration_minutes == config.duration_minutes
        and legacy.model_id == config.model_id
        and legacy.research_tier == config.research_tier
        and legacy.fanout_depth == config.fanout_depth
        and legacy.asset_id == config.asset_id
    )


@midnight_oil_router.post("/jobs/{job_id}/spend-consent")
def post_spend_consent(
    request: Request, job_id: str, body: ConsentBody, response: Response
) -> dict[str, Any]:
    deps, row = _owned(request, job_id)
    owner = _owner(request)
    try:
        config = _config(row)
        recommended = _recommended_cents(row)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
    legacy_job = get_job(job_id, store=deps.jobs)
    if legacy_job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not _legacy_matches_authority(legacy_job, config):
        raise HTTPException(status_code=409, detail="job configuration requires reconciliation")
    if body.use_recommended:
        if body.ceiling_cents is not None:
            raise HTTPException(status_code=400, detail="choose ceiling_cents or use_recommended")
        ceiling = recommended
    elif body.ceiling_cents is None:
        raise HTTPException(status_code=400, detail="ceiling_cents is required")
    else:
        ceiling = body.ceiling_cents
    if ceiling < recommended and not body.force_below:
        raise HTTPException(status_code=400, detail="ceiling is below the recommendation")
    if not 1 <= ceiling <= MAX_CEILING_CENTS:
        raise HTTPException(status_code=400, detail="ceiling_cents is outside authority bounds")

    renewing_expired = False
    if row.operation_state is OperationState.CONSENT_ISSUED:
        if (
            row.approved_ceiling_cents != ceiling
            or row.operation_id is None
            or row.consent_receipt_id is None
        ):
            raise HTTPException(status_code=409, detail="job already has different spend consent")
        try:
            recovery_now = deps.clock_ms()
            token, receipt = deps.consents.recover_unclaimed(
                receipt_id=row.consent_receipt_id,
                expected_operator_id=owner,
                expected_config=config,
                expected_operation_id=row.operation_id,
                expected_ceiling_cents=ceiling,
                now_ms=recovery_now,
                verification_keys=deps.verification_keys,
            )
        except ConsentRejected as exc:
            if exc.reason is ConsentRejection.EXPIRED and row.consent_claimed_at_ms is None:
                renewing_expired = True
            else:
                raise HTTPException(
                    status_code=409,
                    detail="existing spend consent cannot be recovered",
                    headers={"Cache-Control": "no-store"},
                ) from None
        else:
            response.headers["Cache-Control"] = "no-store"
            return {
                "token": token,
                "operation_id": receipt.operation_id,
                "ceiling_cents": receipt.ceiling_cents,
                "issued_at_ms": receipt.issued_at_ms,
                "expires_at_ms": receipt.expires_at_ms,
                "recovered": True,
            }
    if row.operation_state is not OperationState.NONE and not renewing_expired:
        raise HTTPException(status_code=409, detail="job already has spend consent")

    try:
        now = deps.clock_ms()
        operation_id = deps.random_token(24)
        nonce = deps.random_token(32)
        if type(now) is not int or now < 0:
            raise ValueError("invalid clock")
        if (
            type(operation_id) is not str
            or not 16 <= len(operation_id) <= 512
            or type(nonce) is not str
            or not 16 <= len(nonce) <= 512
            or operation_id == nonce
        ):
            raise ValueError("invalid entropy source")
        token = deps.consents.issue(
            operator_id=owner,
            config=config,
            operation_id=operation_id,
            ceiling_cents=ceiling,
            issued_at_ms=now,
            expires_at_ms=now + CONSENT_TTL_MS,
            nonce=nonce,
            key_id=deps.active_key_id,
            signing_key=deps.signing_key,
        )
        receipt: ConsentReceipt = decode_and_verify(token, verification_keys=deps.verification_keys)
        publish = (
            deps.owner_jobs.replace_expired_consent
            if renewing_expired
            else deps.owner_jobs.publish_consent
        )
        publish_kwargs: dict[str, Any] = {
            "owner_user_id": owner,
            "job_id": job_id,
            "expected_version": row.state_version,
            "operation_id": operation_id,
            "approved_ceiling_cents": ceiling,
            "consent_receipt_id": receipt.receipt_id,
            "consent_config_hash": receipt.config_hash,
            "consent_issued_at_ms": receipt.issued_at_ms,
            "consent_expires_at_ms": receipt.expires_at_ms,
        }
        if renewing_expired:
            publish_kwargs["now_ms"] = now
        published = publish(**publish_kwargs)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="spend consent could not be issued",
            headers={"Cache-Control": "no-store"},
        ) from None
    if not published.applied:
        raise HTTPException(
            status_code=409,
            detail="job changed while consent was issued",
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "token": token,
        "operation_id": operation_id,
        "ceiling_cents": ceiling,
        "issued_at_ms": receipt.issued_at_ms,
        "expires_at_ms": receipt.expires_at_ms,
        "renewed": renewing_expired,
    }


@midnight_oil_router.get("/jobs/{job_id}")
def get_job_route(request: Request, response: Response, job_id: str) -> dict[str, Any]:
    deps, authority = _owned(request, job_id)
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    response.headers["Cache-Control"] = "no-store"
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "status": (
            job.status
            if authority.operation_state is OperationState.NONE
            else authority.operation_state.value
        ),
        "operation_state": authority.operation_state.value,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "approved_ceiling_usd": (
            None
            if authority.approved_ceiling_cents is None
            else authority.approved_ceiling_cents / 100
        ),
        "force_below_recommended": job.force_below_recommended,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "graph_projection_state": job.graph_projection_state,
        "graph_node_ids": (
            []
            if job.graph_effect_receipt is None
            else list(job.graph_effect_receipt.node_ids)
        ),
        "graph_deliverable_id": (
            None
            if job.graph_effect_receipt is None
            else job.graph_effect_receipt.deliverable_id
        ),
        "notes": job.notes,
        "view_format": "html",
        "runnable": False,
        "html": job_summary_html(job),
    }


@midnight_oil_router.post("/approve")
def post_approve(request: Request, body: LegacyApproveBody) -> None:
    _owned(request, body.job_id)
    raise HTTPException(status_code=410, detail="use the integer-cent spend-consent endpoint")


def _run_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"}
    )


@midnight_oil_router.post("/run")
def post_run(
    request: Request,
    body: RunBody,
    response: Response,
    spend_consent: str | None = Header(default=None, alias="X-Midnight-Oil-Spend-Consent"),
) -> dict[str, Any]:
    """Consume authority and durably enqueue; never execute provider work."""
    deps = _deps(request)
    try:
        owner = _owner(request)
    except HTTPException:
        raise _run_error(401, "authentication required") from None
    authority = deps.owner_jobs.get_job(owner_user_id=owner, job_id=body.job_id)
    if authority is None:
        raise _run_error(404, "job not found")
    if request.query_params:
        raise _run_error(400, "spend consent is accepted only by header")
    response.headers["Cache-Control"] = "no-store"
    header_values = request.headers.getlist("x-midnight-oil-spend-consent")
    if len(header_values) != 1 or spend_consent is None or not spend_consent:
        raise _run_error(400, "spend consent header is required")
    if (
        authority.operation_id is None
        or authority.approved_ceiling_cents is None
        or authority.consent_receipt_id is None
        or authority.consent_config_hash is None
    ):
        raise _run_error(409, "job has no durable spend authority")
    if deps.operation_queue is None:
        raise _run_error(503, "durable operation queue is unavailable")
    try:
        now = deps.clock_ms()
        config = _config(authority)
        legacy = get_job(body.job_id, store=deps.jobs)
        if legacy is None:
            raise _run_error(404, "job not found")
        if (
            not _legacy_matches_authority(legacy, config)
            or config.canonical_hash() != authority.consent_config_hash
        ):
            raise _run_error(409, "job configuration requires reconciliation")
        claim = deps.consents.claim(
            spend_consent,
            expected_operator_id=owner,
            expected_config=config,
            expected_operation_id=authority.operation_id,
            expected_ceiling_cents=authority.approved_ceiling_cents,
            now_ms=now,
            verification_keys=deps.verification_keys,
            allow_expired_recovery=True,
        )
        if (
            claim.receipt.receipt_id != authority.consent_receipt_id
            or claim.receipt.config_hash != authority.consent_config_hash
        ):
            raise _run_error(409, "spend authority requires reconciliation")
    except ConsentRejected:
        # Deliberately exclude the raw credential and signature from all errors.
        raise HTTPException(
            status_code=403,
            detail="spend consent rejected",
            headers={"Cache-Control": "no-store"},
        ) from None
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError):
        raise _run_error(409, "stored job authority is invalid") from None
    except Exception:
        raise _run_error(503, "spend consent authority is unavailable") from None

    current = authority
    if claim.receipt.receipt_id != authority.consent_receipt_id:
        raise _run_error(409, "consent authority requires reconciliation")
    if current.operation_state is OperationState.CONSENT_ISSUED:
        # A fresh claim permits only this CAS.  A replayed claim may recover the
        # same operation after a claim->CAS crash; operation_id is in the CAS.
        try:
            changed = deps.owner_jobs.compare_and_set(
                owner_user_id=owner,
                job_id=body.job_id,
                expected_version=current.state_version,
                expected_state=OperationState.CONSENT_ISSUED,
                operation_id=claim.receipt.operation_id,
                next_state=OperationState.QUEUED,
                consent_claimed_at_ms=claim.claimed_at_ms,
            )
        except Exception:
            raise _run_error(503, "operation transition is unavailable") from None
        current = changed.job or current
    elif claim.claimed_now:
        # A newly consumed receipt cannot legitimately observe a later state.
        raise _run_error(409, "operation state conflicts with consent")

    # A lost CAS race converges by re-reading authority.  Never infer success.
    try:
        latest = deps.owner_jobs.get_job(owner_user_id=owner, job_id=body.job_id)
    except Exception:
        raise _run_error(503, "operation authority is unavailable") from None
    if latest is None or latest.operation_id != claim.receipt.operation_id:
        raise _run_error(409, "operation conflicts with durable authority")
    current = latest
    if current.operation_state is OperationState.CONSENT_ISSUED:
        raise _run_error(503, "operation transition did not persist")

    try:
        queued = deps.operation_queue.get(claim.receipt.operation_id)
    except Exception:
        raise _run_error(503, "operation queue is unavailable") from None
    requested_options: dict[str, object] = {
        "max_steps": body.max_steps,
        "auto_deposit": body.auto_deposit,
        "draft_combined": body.draft_combined,
        "force_offline": body.force_offline,
    }
    if current.operation_state is OperationState.QUEUED and queued is None:
        try:
            queued, _ = deps.operation_queue.enqueue_once(
                operation_id=claim.receipt.operation_id,
                owner_user_id=owner,
                job_id=body.job_id,
                enqueued_at_ms=now,
                options=requested_options,
            )
        except ValueError:
            raise _run_error(409, "operation queue conflicts with authority") from None
        except Exception:
            raise _run_error(503, "operation enqueue is unavailable") from None
    elif queued is not None:
        if queued.owner_user_id != owner or queued.job_id != body.job_id:
            raise _run_error(409, "operation queue conflicts with authority")
        if queued.options != requested_options:
            raise _run_error(409, "operation replay options conflict with durable queue")
    return {
        "job_id": body.job_id,
        "operation_id": claim.receipt.operation_id,
        "state": current.operation_state.value,
    }


@midnight_oil_router.post("/deposit")
def post_deposit(request: Request, body: DepositBody) -> dict[str, Any]:
    from interfaces.research.api.engagement_routes import _eng, get_bench_usage_store
    from substrate.engagement_spine import progress_payload

    deps, authority = _owned(request, body.job_id)
    terminal = {
        OperationState.COMPLETE,
        OperationState.FAILED,
        OperationState.STEP_CAPPED,
        OperationState.BUDGET_HALTED,
        OperationState.TIMED_OUT,
        OperationState.FAILED_RECONCILE,
    }
    if authority.operation_state not in terminal:
        raise HTTPException(
            status_code=409,
            detail="deposit is disabled until durable execution reaches a terminal state",
        )
    job = get_job(body.job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        config = _config(authority)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
    if not _legacy_matches_authority(job, config):
        raise HTTPException(status_code=409, detail="job configuration requires reconciliation")
    try:
        deposit = deposit_job_results(
            body.job_id,
            job_store=deps.jobs,
            engagement_store=_eng(),
            job_snapshot=job,
            draft_combined=body.draft_combined,
            bench_usage_store=get_bench_usage_store(create_if_missing=True),
            record_progress=body.record_progress,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    progress: dict[str, Any] | None = None
    if deposit.spawn_ids:
        try:
            progress = progress_payload(
                deposit.spawn_ids[0],
                store=_eng(),
                include_html=body.include_progress_html,
            )
        except (KeyError, ValueError):
            progress = None
    return {
        "job_id": deposit.job_id,
        "asset_id": deposit.asset_id,
        "document_id": deposit.document_id,
        "twin_count": deposit.twin_count,
        "spawn_ids": list(deposit.spawn_ids),
        "draft_combined": deposit.draft_combined,
        "usage_recorded": deposit.usage_recorded,
        "usage_event": deposit.usage_event,
        "progress_seeded": deposit.progress_seeded,
        "progress": progress,
        "job_status": (get_job(body.job_id, store=deps.jobs) or job).status,
        "view_format": "html",
        "html": deposit.html,
        "product_panel": "midnight_oil_deposit",
        "source": "midnight_oil.deposit_job_results",
    }


@midnight_oil_router.get("/live-step-status")
def get_live_step_status(request: Request) -> dict[str, Any]:
    _owner(request)
    from substrate.midnight_oil import live_step_status_payload

    return live_step_status_payload()


def register_midnight_oil_routes(
    app: FastAPI, *, dependencies: MidnightOilDependencies | None = None
) -> None:
    if dependencies is None:
        raise RuntimeError("Midnight Oil durable dependencies must be configured at startup")
    setattr(app.state, _DEPENDENCIES, dependencies)
    app.include_router(midnight_oil_router)


__all__ = [
    "MidnightOilDependencies",
    "midnight_oil_preflight_router",
    "midnight_oil_router",
    "post_midnight_oil_preflight",
    "post_midnight_oil_execute",
    "register_midnight_oil_routes",
]
