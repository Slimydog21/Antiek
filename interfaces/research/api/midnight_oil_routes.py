"""Authenticated, owner-bound Midnight Oil consent HTTP surface.

All job authority is loaded through the durable owner predicate before a route
touches job data. Dispatch remains disabled: this module can create jobs,
publish one spend-consent authorization, and render owner-scoped reads, but it
cannot execute or deposit work.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from substrate.midnight_oil import create_with_recommended_ceiling, job_summary_html
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    MidnightOilJob,
    MidnightOilJobAuthority,
    OperationState,
)
from substrate.midnight_oil.job_store import SqliteDurableJobStore, create_production_job_store
from substrate.midnight_oil.operation_queue import DurableOperationQueue, OperationQueue
from substrate.midnight_oil.spend_consent import (
    MAX_CEILING_CENTS,
    ConsentReceipt,
    ConsentRejected,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

_DEPENDENCIES = "midnight_oil_dependencies"
CONSENT_TTL_MS = 15 * 60 * 1000


def _require_identity(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=401, detail="authentication required")
    return value.strip()


class _AuthenticatedRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route_handler = super().get_route_handler()

        async def authenticated_handler(request: Request) -> Response:
            try:
                if request.url.path == "/midnight-oil/run" and request.scope.get("query_string"):
                    # Query credentials are invalid, but the raw request target is
                    # also an access-log boundary. Remove it before server logging.
                    request.state.midnight_oil_had_query = True
                    request.scope["query_string"] = b""
                _require_identity(request)
                response = await route_handler(request)
            except RequestValidationError as exc:
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": [_sanitized_validation_error(error) for error in exc.errors()]
                    },
                    headers={"Cache-Control": "no-store"},
                )
            except HTTPException as exc:
                headers = dict(exc.headers or {})
                headers["Cache-Control"] = "no-store"
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=headers,
                )
            except Exception:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Midnight Oil service unavailable"},
                    headers={"Cache-Control": "no-store"},
                )
            response.headers["Cache-Control"] = "no-store"
            return response

        return authenticated_handler


def _sanitized_validation_error(error: Mapping[str, object]) -> dict[str, object]:
    sanitized = {key: error[key] for key in ("type", "loc", "msg") if key in error}
    context = error.get("ctx")
    if isinstance(context, Mapping):
        sanitized["ctx"] = {
            str(key): value
            for key, value in context.items()
            if value is None or type(value) in {bool, int, float}
        }
    return sanitized


midnight_oil_router = APIRouter(
    prefix="/midnight-oil", tags=["midnight-oil"], route_class=_AuthenticatedRoute
)


class OwnerAuthorityStore(Protocol):
    def put_job_for_owner(self, owner_user_id: str, job: MidnightOilJob) -> MidnightOilJob: ...

    def get_job_for_owner(self, job_id: str, owner_user_id: str) -> MidnightOilJob | None: ...

    def compare_and_set_authority(
        self,
        job_id: str,
        owner_user_id: str,
        *,
        expected_version: int,
        expected_state: OperationState,
        expected_operation_id: str | None,
        operation_id: str | None,
        next_state: OperationState,
        approved_ceiling_cents: object,
        consent_granted_by_user_id: object,
        consent_recorded_at_ms: object,
        consent_note: object,
        force_below_recommended: object,
        dispatch_claimed_at_ms: object = ...,
    ) -> MidnightOilJob | None: ...


def _system_clock_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True, repr=False)
class MidnightOilDependencies:
    jobs: OwnerAuthorityStore
    consents: SpendConsentStore
    active_key_id: str
    signing_key: bytes
    verification_keys: Mapping[str, bytes]
    operation_queue: OperationQueue | None = None
    clock_ms: Callable[[], int] = _system_clock_ms
    random_bytes: Callable[[int], bytes] = secrets.token_bytes
    test_mode: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.active_key_id) is not str
            or not self.active_key_id
            or self.active_key_id != self.active_key_id.strip()
            or len(self.active_key_id) > 64
        ):
            raise ValueError("the active consent key id must be canonical")
        if type(self.signing_key) is not bytes or len(self.signing_key) < 32:
            raise ValueError("a 256-bit consent signing key is required")
        if not self.verification_keys:
            raise ValueError("a consent verification keyring is required")
        for key_id, key in self.verification_keys.items():
            if (
                type(key_id) is not str
                or not key_id
                or key_id != key_id.strip()
                or len(key_id) > 64
            ):
                raise ValueError("verification key ids must be canonical")
            if type(key) is not bytes or len(key) < 32:
                raise ValueError("verification keys must be at least 256 bits")
        if self.verification_keys.get(self.active_key_id) != self.signing_key:
            raise ValueError("the active signing key must be present in the verification keyring")
        if not self.test_mode:
            if (
                type(self.jobs) is not SqliteDurableJobStore
                or type(self.consents) is not SpendConsentStore
                or type(self.operation_queue) is not DurableOperationQueue
            ):
                raise ValueError("production Midnight Oil requires durable stores")
            if (
                self.clock_ms is not _system_clock_ms
                or self.random_bytes is not secrets.token_bytes
            ):
                raise ValueError("production Midnight Oil requires system clock and CSPRNG")


def _decode_key(value: object, *, field_name: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{field_name} is required")
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise RuntimeError(f"{field_name} must be canonical base64") from exc
    if len(key) < 32:
        raise RuntimeError(f"{field_name} must decode to at least 32 bytes")
    return key


def midnight_oil_enabled(value: str | None) -> bool:
    if value is not None and value != value.strip():
        raise RuntimeError("ANTIEK_MIDNIGHT_OIL_ENABLED must be an explicit boolean")
    normalized = "" if value is None else value.strip().lower()
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError("ANTIEK_MIDNIGHT_OIL_ENABLED must be an explicit boolean")


def production_dependencies_from_env(
    environ: Mapping[str, str] | None = None,
) -> MidnightOilDependencies:
    """Build live dependencies or refuse startup on any missing/malformed value."""
    env = os.environ if environ is None else environ
    job_path = env.get("ANTIEK_MIDNIGHT_OIL_DB", "").strip()
    consent_path = env.get("ANTIEK_MIDNIGHT_OIL_CONSENT_DB", "").strip()
    queue_path = env.get("ANTIEK_MIDNIGHT_OIL_QUEUE_DB", "").strip()
    active_key_id = env.get("ANTIEK_MIDNIGHT_OIL_ACTIVE_KEY_ID", "")
    if not job_path or not consent_path or not queue_path or not active_key_id:
        raise RuntimeError("durable Midnight Oil paths and active key id are required")
    if active_key_id != active_key_id.strip() or len(active_key_id) > 64:
        raise RuntimeError("active consent key id must be canonical")
    signing_key = _decode_key(
        env.get("ANTIEK_MIDNIGHT_OIL_SIGNING_KEY_B64"), field_name="active signing key"
    )
    raw_keyring = env.get("ANTIEK_MIDNIGHT_OIL_VERIFY_KEYS_JSON", "")
    try:
        decoded_keyring = json.loads(raw_keyring)
    except json.JSONDecodeError as exc:
        raise RuntimeError("consent verification keyring must be valid JSON") from exc
    if not isinstance(decoded_keyring, dict):
        raise RuntimeError("consent verification keyring must be a JSON object")
    keyring: dict[str, bytes] = {}
    for key_id, value in decoded_keyring.items():
        if not isinstance(key_id, str) or not key_id or key_id != key_id.strip():
            raise RuntimeError("verification key ids must be canonical strings")
        keyring[key_id] = _decode_key(value, field_name=f"verification key {key_id!r}")
    return MidnightOilDependencies(
        jobs=create_production_job_store(job_path),
        consents=SpendConsentStore(consent_path),
        active_key_id=active_key_id,
        signing_key=signing_key,
        verification_keys=keyring,
        operation_queue=DurableOperationQueue(queue_path),
    )


def _dependencies(request: Request) -> MidnightOilDependencies:
    value = getattr(request.app.state, _DEPENDENCIES, None)
    if not isinstance(value, MidnightOilDependencies):
        raise HTTPException(status_code=503, detail="Midnight Oil is not configured")
    return value


def _owner(request: Request) -> str:
    return _require_identity(request)


def _owned(request: Request, job_id: str) -> tuple[MidnightOilDependencies, MidnightOilJob]:
    owner = _owner(request)
    dependencies = _dependencies(request)
    job = dependencies.jobs.get_job_for_owner(job_id, owner)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return dependencies, job


class CreateJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goals: list[StrictStr] = Field(min_length=1, max_length=64)
    duration_minutes: StrictInt = Field(ge=1, le=10_080)
    model_id: StrictStr | None = Field(default=None, max_length=256)
    fanout_depth: StrictInt = Field(default=3, ge=1, le=64)
    asset_id: StrictStr | None = Field(default=None, max_length=256)
    job_id: StrictStr | None = Field(default=None, max_length=256)
    research_tier: StrictStr | None = Field(default=None, max_length=32)

    @field_validator("goals")
    @classmethod
    def validate_goal_bounds(cls, goals: list[str]) -> list[str]:
        if any(len(goal) > 4_096 for goal in goals) or sum(len(goal) for goal in goals) > 65_536:
            raise ValueError("goal text exceeds configured bounds")
        return goals


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ceiling_cents: StrictInt | None = Field(default=None, ge=1, le=MAX_CEILING_CENTS)
    use_recommended: StrictBool = False
    force_below: StrictBool = False


class LegacyApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: StrictStr = Field(min_length=1, max_length=256)
    ceiling_cents: StrictInt | None = Field(default=None, ge=1, le=MAX_CEILING_CENTS)
    use_recommended: StrictBool = False
    force_below: StrictBool = False


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: StrictStr = Field(min_length=1, max_length=256)
    max_steps: StrictInt | None = Field(default=None, ge=1, le=100_000)
    spent_per_goal: float = 0.05
    auto_deposit: StrictBool = False
    draft_combined: StrictBool = True
    force_offline: StrictBool = False


class DepositBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: StrictStr = Field(min_length=1, max_length=256)
    draft_combined: StrictBool = True
    record_progress: StrictBool = True
    mark_complete: StrictBool = True
    include_progress_html: StrictBool = True


def _random_identifier(dependencies: MidnightOilDependencies, byte_count: int) -> str:
    raw = dependencies.random_bytes(byte_count)
    if type(raw) is not bytes or len(raw) != byte_count:
        raise RuntimeError("invalid CSPRNG result")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _config(job: MidnightOilJob) -> JobConsentConfig:
    return JobConsentConfig(
        job_id=job.job_id,
        goals=job.goals,
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
        asset_id=job.asset_id,
    )


def _recommended_cents(job: MidnightOilJob) -> int:
    cents = int(
        (Decimal(str(job.recommended_price_ceiling_usd)) * 100).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    if not 1 <= cents <= MAX_CEILING_CENTS:
        raise ValueError("stored recommended ceiling is invalid")
    return cents


def _job_response(job: MidnightOilJob) -> dict[str, Any]:
    authority = job.authority
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": job.fanout_depth,
        "status": job.status,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "approved_ceiling_cents": None if authority is None else authority.approved_ceiling_cents,
        "approved_ceiling_usd": (
            None
            if authority is None or authority.approved_ceiling_cents is None
            else authority.approved_ceiling_cents / 100
        ),
        "force_below_recommended": job.force_below_recommended,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "notes": job.notes,
        "view_format": "html",
        "runnable": False,
        "html": job_summary_html(job),
    }


@midnight_oil_router.post("/create")
def post_create(request: Request, body: CreateJobBody) -> dict[str, Any]:
    owner = _owner(request)
    dependencies = _dependencies(request)
    staging = InMemoryJobStore()
    try:
        result = create_with_recommended_ceiling(
            body.goals,
            body.duration_minutes,
            store=staging,
            model_id=body.model_id,
            fanout_depth=body.fanout_depth,
            job_id=body.job_id or f"moil_{_random_identifier(dependencies, 16)}",
            asset_id=body.asset_id,
            research_tier=body.research_tier,
        )
        owned = replace(
            result.job,
            authority=MidnightOilJobAuthority(owner_user_id=owner),
        )
        stored = dependencies.jobs.put_job_for_owner(owner, owned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=503, detail="job creation unavailable") from None
    return _job_response(stored)


@midnight_oil_router.get("/jobs/{job_id}")
def get_job_route(request: Request, job_id: str) -> dict[str, Any]:
    _, job = _owned(request, job_id)
    return _job_response(job)


@midnight_oil_router.post("/jobs/{job_id}/spend-consent")
def post_spend_consent(
    request: Request, job_id: str, body: ConsentBody, response: Response
) -> dict[str, Any]:
    dependencies, job = _owned(request, job_id)
    owner = _owner(request)
    authority = job.authority
    if authority is None or authority.operation_state != "awaiting_approval":
        raise HTTPException(status_code=409, detail="job already has spend consent")
    try:
        config = _config(job)
        recommended = _recommended_cents(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
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
    try:
        now = dependencies.clock_ms()
        if type(now) is not int or now < 0:
            raise ValueError("invalid clock")
        operation_id = _random_identifier(dependencies, 24)
        nonce = _random_identifier(dependencies, 32)
        token = dependencies.consents.issue(
            operator_id=owner,
            config=config,
            operation_id=operation_id,
            ceiling_cents=ceiling,
            issued_at_ms=now,
            expires_at_ms=now + CONSENT_TTL_MS,
            nonce=nonce,
            key_id=dependencies.active_key_id,
            signing_key=dependencies.signing_key,
        )
        receipt: ConsentReceipt = decode_and_verify(
            token, verification_keys=dependencies.verification_keys
        )
        published = dependencies.jobs.compare_and_set_authority(
            job_id,
            owner,
            expected_version=authority.state_version,
            expected_state="awaiting_approval",
            expected_operation_id=None,
            operation_id=operation_id,
            next_state="approved",
            approved_ceiling_cents=ceiling,
            consent_granted_by_user_id=owner,
            consent_recorded_at_ms=now,
            consent_note="spend-consent-v1",
            force_below_recommended=body.force_below,
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="spend consent could not be issued",
            headers={"Cache-Control": "no-store"},
        ) from None
    if published is None:
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
        "expires_at_ms": receipt.expires_at_ms,
        "job_id": published.job_id,
        "status": "approved",
        "force_below_recommended": published.force_below_recommended,
    }


@midnight_oil_router.post("/approve")
def post_approve(request: Request, body: LegacyApproveBody, response: Response) -> dict[str, Any]:
    return post_spend_consent(
        request,
        body.job_id,
        ConsentBody(
            ceiling_cents=body.ceiling_cents,
            use_recommended=body.use_recommended,
            force_below=body.force_below,
        ),
        response,
    )


def _dispatch_disabled(request: Request, job_id: str) -> None:
    _owned(request, job_id)
    raise HTTPException(status_code=409, detail="Midnight Oil dispatch is disabled")


@midnight_oil_router.post("/run")
def post_run(
    request: Request,
    body: RunBody,
    spend_consent: str | None = Header(default=None, alias="X-Midnight-Oil-Spend-Consent"),
) -> dict[str, object]:
    """Claim durable authority and enqueue it; provider work belongs to workers."""
    owner = _owner(request)
    dependencies, durable_job = _owned(request, body.job_id)
    authority = durable_job.authority
    if getattr(request.state, "midnight_oil_had_query", False):
        raise HTTPException(status_code=400, detail="spend consent is accepted only by header")
    values = request.headers.getlist("x-midnight-oil-spend-consent")
    if len(values) != 1 or not spend_consent:
        raise HTTPException(status_code=400, detail="spend consent header is required")
    if (
        authority is None
        or authority.operation_id is None
        or authority.approved_ceiling_cents is None
        or dependencies.operation_queue is None
    ):
        raise HTTPException(status_code=409, detail="job has no durable spend authority")
    config = _config(durable_job)
    try:
        now = dependencies.clock_ms()
        claim = dependencies.consents.claim(
            spend_consent,
            expected_operator_id=owner,
            expected_config=config,
            expected_operation_id=authority.operation_id,
            expected_ceiling_cents=authority.approved_ceiling_cents,
            now_ms=now,
            verification_keys=dependencies.verification_keys,
            allow_expired_recovery=True,
        )
    except ConsentRejected:
        raise HTTPException(status_code=403, detail="spend consent rejected") from None

    if authority.operation_state == "approved":
        changed = dependencies.jobs.compare_and_set_authority(
            body.job_id,
            owner,
            expected_version=authority.state_version,
            expected_state="approved",
            expected_operation_id=authority.operation_id,
            operation_id=authority.operation_id,
            next_state="dispatch_claimed",
            dispatch_claimed_at_ms=claim.claimed_at_ms,
        )
        if changed is not None:
            durable_job = changed

    latest = dependencies.jobs.get_job_for_owner(body.job_id, owner)
    if latest is None or latest.authority is None:
        raise HTTPException(status_code=503, detail="operation authority is unavailable")
    current = latest.authority
    if current.operation_id != claim.receipt.operation_id:
        raise HTTPException(status_code=409, detail="operation conflicts with durable authority")
    if current.operation_state == "approved":
        raise HTTPException(status_code=503, detail="operation transition did not persist")

    queue = dependencies.operation_queue
    queued = queue.get(current.operation_id)
    if current.operation_state == "dispatch_claimed" and queued is None:
        queued, _ = queue.enqueue_once(
            operation_id=current.operation_id,
            owner_user_id=owner,
            job_id=body.job_id,
            enqueued_at_ms=now,
            options={
                "max_steps": None,
                "auto_deposit": False,
                "draft_combined": True,
                "force_offline": True,
            },
        )
    if queued is not None and (queued.owner_user_id, queued.job_id) != (owner, body.job_id):
        raise HTTPException(status_code=409, detail="operation queue conflicts with authority")
    return {
        "job_id": body.job_id,
        "operation_id": current.operation_id,
        "state": current.operation_state,
    }


@midnight_oil_router.post("/deposit")
def post_deposit(request: Request, body: DepositBody) -> None:
    _dispatch_disabled(request, body.job_id)


@midnight_oil_router.get("/live-step-status")
def get_live_step_status(request: Request) -> dict[str, object]:
    _owner(request)
    return {"offline_honest": True, "dispatch_enabled": False}


def register_midnight_oil_routes(
    app: FastAPI, dependencies: MidnightOilDependencies | None = None
) -> None:
    if dependencies is not None:
        setattr(app.state, _DEPENDENCIES, dependencies)
    app.include_router(midnight_oil_router)


__all__ = [
    "MidnightOilDependencies",
    "midnight_oil_enabled",
    "midnight_oil_router",
    "production_dependencies_from_env",
    "register_midnight_oil_routes",
]
