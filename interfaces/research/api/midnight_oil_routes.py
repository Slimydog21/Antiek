"""Authenticated, owner-bound Midnight Oil HTTP surface.

The durable owner store is the authorization boundary.  The legacy job store
remains an execution/detail substrate until the worker migration, but is never
queried until ownership has been established.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from substrate.engagement_spine.store import EngagementStore, FileEngagementStore
from substrate.midnight_oil import (
    LiveExecutionPlan,
    MidnightOilExecutionReceipt,
    MidnightOilExecutionRequest,
    MidnightOilPreflight,
    MidnightOilProductResult,
    MidnightOilRequest,
    create_with_recommended_ceiling,
    deposit_job_results,
    execute_midnight_oil,
    get_job,
    job_summary_html,
    preflight_midnight_oil,
    product_result_html,
)
from substrate.midnight_oil.budget_ledger import BudgetLedger, ReservationNotFound
from substrate.midnight_oil.consent_stage_coordinator import ConsentStagePlanCoordinator
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    JobStore,
    MidnightOilJob,
    put_job_state,
)
from substrate.midnight_oil.job_store import (
    DurableOwnerJobStore,
    OperationState,
    OwnerJob,
    OwnerJobStore,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue, OperationQueue
from substrate.midnight_oil.publication_capability import (
    PublicationCapabilityRegistry,
    require_pinned_publication_capability,
)
from substrate.midnight_oil.session_flywheel import context_binding_sha256
from substrate.midnight_oil.spend_consent import (
    MAX_CEILING_CENTS,
    ConsentReceipt,
    ConsentRejected,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)
from substrate.midnight_oil.status import LifecycleIntegrityError, project_lifecycle_status
from substrate.midnight_oil.swarm_plan import SwarmLivePlan, build_stage_plan

midnight_oil_router = APIRouter(prefix="/midnight-oil", tags=["midnight-oil"])
midnight_oil_preflight_router = APIRouter(prefix="/research/midnight-oil", tags=["deep-research"])
_DEPENDENCIES = "midnight_oil_dependencies"
_PRIVATE_AUTHORITY_RESOLVER = "midnight_oil_private_authority_resolver"
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
    engagement_store: EngagementStore | None = None
    live_plan_resolver: Callable[[MidnightOilJob], LiveExecutionPlan | SwarmLivePlan] | None = None
    consent_stage_coordinator: ConsentStagePlanCoordinator | None = None
    publication_capabilities: PublicationCapabilityRegistry = field(
        default_factory=PublicationCapabilityRegistry
    )
    publication_completion_margin_ms: int = 0
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
        if (
            type(self.publication_completion_margin_ms) is not int
            or not 0 <= self.publication_completion_margin_ms <= 3_600_000
        ):
            raise ValueError("publication completion margin is invalid")
        if not self.test_mode:
            if (
                type(self.owner_jobs) is not DurableOwnerJobStore
                or type(self.jobs) is not DurableJobStore
                or type(self.consents) is not SpendConsentStore
                or type(self.operation_queue) is not DurableOperationQueue
                or type(self.engagement_store) is not FileEngagementStore
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


def _private_authority_resolver(request: Request) -> object | None:
    return getattr(request.app.state, _PRIVATE_AUTHORITY_RESOLVER, None)


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


def _owner_payload(
    job: Any,
    *,
    live_plan: LiveExecutionPlan | None = None,
    swarm_plan: SwarmLivePlan | None = None,
    context_binding: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if live_plan is not None and swarm_plan is not None:
        raise ValueError("legacy and swarm live authority cannot coexist")
    recommended_cents = int(
        (Decimal(str(job.recommended_price_ceiling_usd)) * 100).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    binding = context_binding or {}
    payload: dict[str, object] = {
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
        "swarm_live_plan_json": (None if swarm_plan is None else swarm_plan.model_dump_json()),
        "swarm_live_plan_hash": None if swarm_plan is None else swarm_plan.plan_hash,
        "execution_id": binding.get("execution_id"),
        "collective_unit_id": binding.get("collective_unit_id"),
        "collective_preview_sha256": binding.get("collective_preview_sha256"),
        "floating_session_id": binding.get("floating_session_id"),
        "floating_spawn_id": binding.get("floating_spawn_id"),
        "context_binding_sha256": binding.get("context_binding_sha256"),
        "context_parent_asset_id": binding.get("context_parent_asset_id"),
        "publication_manifest_sha256": binding.get("publication_manifest_sha256"),
        "publication_manifest_json": binding.get("publication_manifest_json"),
        "publication_preflight_ready": binding.get("publication_preflight_ready"),
        "publication_capability_sha256": binding.get(
            "publication_capability_sha256"
        ),
        "publication_capability_id": binding.get("publication_capability_id"),
        "publication_capability_expires_at_ms": binding.get(
            "publication_capability_expires_at_ms"
        ),
    }
    private_names = (
        "publication_manifest_schema_version",
        "owner_private_publication_authority_json",
        "owner_private_publication_authority_sha256",
        "private_output_policy_sha256",
        "context_binding_schema_version",
        "owner_private_execution_state",
    )
    private_values = tuple(binding.get(name) for name in private_names)
    if any(value is not None for value in private_values):
        if any(value is None for value in private_values):
            raise ValueError("owner-private context binding is incomplete")
        payload.update(dict(zip(private_names, private_values, strict=True)))
        for name in (
            "publication_preflight_ready",
            "publication_capability_sha256",
            "publication_capability_id",
            "publication_capability_expires_at_ms",
        ):
            payload.pop(name, None)
        if swarm_plan is None:
            raise ValueError("owner-private execution requires signed swarm authority")
        from substrate.midnight_oil.private_provider_authority import (
            parse_owner_private_publication_authority_json,
        )

        private_authority = parse_owner_private_publication_authority_json(
            str(binding["owner_private_publication_authority_json"])
        )
        for selection in private_authority.selections:
            if any(
                selection.route_key not in swarm_plan.role(role).allowed_routes
                for role in selection.required_router_roles
            ):
                raise ValueError("owner-private swarm topology conflicts")
    return payload


def create_job_authority(
    *,
    deps: MidnightOilDependencies,
    owner: str,
    body: CreateJobBody,
    job_id: str | None = None,
    asset_id: str | None = None,
    context_binding: Mapping[str, object] | None = None,
) -> MidnightOilProductResult:
    """Create or replay one exact owner job without issuing spend authority."""
    if job_id is None:
        job_id = deps.random_token(20)
    if asset_id is None:
        asset_id = deps.random_token(28)
    existing = deps.owner_jobs.get_job(owner_user_id=owner, job_id=job_id)
    if existing is not None:
        _require_publication_swarm_authority(existing)
        config = _config(existing)
        expected_binding = {
            key: value for key, value in dict(context_binding or {}).items() if value is not None
        }
        binding_keys = (
            "execution_id",
            "collective_unit_id",
            "collective_preview_sha256",
            "floating_session_id",
            "floating_spawn_id",
            "context_binding_sha256",
            "context_parent_asset_id",
            "publication_manifest_sha256",
            "publication_manifest_json",
            "publication_preflight_ready",
            "publication_capability_sha256",
            "publication_capability_id",
            "publication_capability_expires_at_ms",
            "publication_manifest_schema_version",
            "owner_private_publication_authority_json",
            "owner_private_publication_authority_sha256",
            "private_output_policy_sha256",
            "context_binding_schema_version",
            "owner_private_execution_state",
        )
        stored_binding = {
            key: existing.payload[key]
            for key in binding_keys
            if existing.payload.get(key) is not None
        }
        if (
            config.goals != tuple(body.goals)
            or config.duration_minutes != body.duration_minutes
            or config.model_id != body.model_id
            or config.fanout_depth != body.fanout_depth
            or config.research_tier != (body.research_tier or "deep")
            or config.asset_id != asset_id
            or stored_binding != expected_binding
        ):
            raise ValueError("job identity conflicts with existing authority")
        existing_detail = get_job(job_id, store=deps.jobs)
        if existing_detail is None:
            if (
                existing.operation_state is not OperationState.NONE
                or existing.state_version != 0
                or existing.consent_receipt_id is not None
                or existing.operation_id is not None
                or existing.dispatch_started_at_ms is not None
            ):
                raise ValueError("non-pristine job detail requires reconciliation")
            display = existing.payload.get("display_usd")
            if not isinstance(display, (int, float)) or isinstance(display, bool):
                raise ValueError("stored job recommendation requires reconciliation")
            existing_detail = MidnightOilJob(
                job_id=job_id,
                goals=config.goals,
                duration_minutes=config.duration_minutes,
                model_id=config.model_id,
                recommended_price_ceiling_usd=float(display),
                status="awaiting_approval",
                asset_id=config.asset_id,
                research_tier=config.research_tier,
                fanout_depth=config.fanout_depth,
            )
            put_job_state(existing_detail, store=deps.jobs)
        elif not _legacy_matches_authority(existing_detail, config):
            raise ValueError("job detail conflicts with existing authority")
        return MidnightOilProductResult(
            job=existing_detail,
            recommended_price_ceiling_usd=existing_detail.recommended_price_ceiling_usd,
        )
    try:
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
            if not isinstance(live_plan, (LiveExecutionPlan, SwarmLivePlan)):
                raise RuntimeError("live execution plan resolver returned invalid data")
        else:
            live_plan = None
        authority = OwnerJob(
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
            payload=_owner_payload(
                result.job,
                live_plan=(live_plan if isinstance(live_plan, LiveExecutionPlan) else None),
                swarm_plan=(live_plan if isinstance(live_plan, SwarmLivePlan) else None),
                context_binding=context_binding,
            ),
        )
        _require_publication_swarm_authority(authority)
        try:
            deps.owner_jobs.put_job(authority)
        except ValueError:
            return create_job_authority(
                deps=deps,
                owner=owner,
                body=body,
                job_id=job_id,
                asset_id=asset_id,
                context_binding=context_binding,
            )
        legacy_row = staging.get_job(result.job.job_id)
        if legacy_row is None:
            raise RuntimeError("staged Midnight Oil job disappeared")
        persisted_row = deps.jobs.get_job(result.job.job_id)
        if persisted_row is not None:
            if persisted_row != legacy_row:
                raise ValueError("job detail conflicts with existing authority")
        else:
            try:
                deps.jobs.put_job(legacy_row)
            except Exception:
                # A write may commit and still raise. Delete authority only after a
                # successful read proves the detail row was not persisted.
                try:
                    persisted_row = deps.jobs.get_job(result.job.job_id)
                    read_confirmed = True
                except Exception:
                    persisted_row = None
                    read_confirmed = False
                if read_confirmed and persisted_row is None:
                    deps.owner_jobs.delete_uninitialized_job(
                        owner_user_id=owner, job_id=result.job.job_id
                    )
                raise
        return result
    except (TypeError, AttributeError):
        raise ValueError("job creation material is invalid") from None


def create_owner_private_job_authority(
    *,
    deps: MidnightOilDependencies,
    owner: str,
    body: CreateJobBody,
    job_id: str,
    asset_id: str,
    execution_id: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
    floating_session_id: str,
    floating_spawn_id: str,
    parent_asset_id: str,
    manifest: Any,
    private_authority_resolver: Any,
    now_ms: int,
) -> MidnightOilProductResult:
    """Persist complete v2 authority internally without exposing a route."""

    from substrate.midnight_oil.private_provider_authority import (
        LivePrivateProviderAuthorityResolver,
        canonical_owner_private_publication_authority_json,
    )
    from substrate.midnight_oil.private_provider_policy import (
        OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    )
    from substrate.midnight_oil.publication_authority_v2 import (
        ReviewedPublicationManifestV2,
    )

    if (
        not isinstance(manifest, ReviewedPublicationManifestV2)
        or not isinstance(
            private_authority_resolver, LivePrivateProviderAuthorityResolver
        )
        or manifest.collective_unit_id != collective_unit_id
        or manifest.collective_preview_sha256 != collective_preview_sha256
        or type(now_ms) is not int
        or isinstance(now_ms, bool)
        or now_ms < 0
    ):
        raise ValueError("owner-private job authority input conflicts")
    required_until_ms = (
        now_ms
        + CONSENT_TTL_MS
        + body.duration_minutes * 60_000
        + deps.publication_completion_margin_ms
    )
    private_authority = private_authority_resolver.resolve(
        manifest,
        now_ms=now_ms,
        required_until_ms=required_until_ms,
    )
    binding_hash = context_binding_sha256(
        owner_id=owner,
        execution_id=execution_id,
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
        floating_session_id=floating_session_id,
        floating_spawn_id=floating_spawn_id,
        parent_asset_id=parent_asset_id,
        duration_minutes=body.duration_minutes,
        model_id=body.model_id,
        research_tier=body.research_tier or "deep",
        fanout_depth=body.fanout_depth,
        publication_manifest_sha256=manifest.manifest_sha256,
        publication_manifest_schema_version=2,
        owner_private_publication_authority_sha256=(
            private_authority.authority_sha256
        ),
        private_output_policy_sha256=OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    )
    binding: dict[str, object] = {
        "execution_id": execution_id,
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "floating_session_id": floating_session_id,
        "floating_spawn_id": floating_spawn_id,
        "context_binding_sha256": binding_hash,
        "context_parent_asset_id": parent_asset_id,
        "publication_manifest_schema_version": 2,
        "publication_manifest_sha256": manifest.manifest_sha256,
        "publication_manifest_json": manifest.model_dump_json(),
        "owner_private_publication_authority_json": (
            canonical_owner_private_publication_authority_json(private_authority)
        ),
        "owner_private_publication_authority_sha256": (
            private_authority.authority_sha256
        ),
        "private_output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
        "context_binding_schema_version": 2,
        "owner_private_execution_state": "propagated_disabled",
    }
    result = create_job_authority(
        deps=deps,
        owner=owner,
        body=body,
        job_id=job_id,
        asset_id=asset_id,
        context_binding=binding,
    )
    from substrate.midnight_oil.private_provider_authority import (
        prospective_owner_private_queue_commitment_from_payload,
        recompute_owner_private_consent_config,
    )

    reopened = deps.owner_jobs.get_job(owner_user_id=owner, job_id=job_id)
    if reopened is None:
        raise RuntimeError("owner-private authority disappeared after persistence")
    recompute_owner_private_consent_config(reopened, result.job).canonical_hash()
    prospective_owner_private_queue_commitment_from_payload(reopened.payload)
    return result


@midnight_oil_router.post("/create")
def post_create(request: Request, body: CreateJobBody) -> dict[str, Any]:
    try:
        result = create_job_authority(deps=_deps(request), owner=_owner(request), body=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError):
        raise HTTPException(status_code=503, detail="job creation unavailable") from None
    out = result.to_dict()
    out["html"] = product_result_html(result)
    return out


def _config(row: OwnerJob) -> JobConsentConfig:
    payload = row.payload
    from substrate.midnight_oil.private_provider_authority import (
        owner_private_authority_from_payload,
    )
    from substrate.midnight_oil.publication_sources import manifest_from_authority

    private_authority = owner_private_authority_from_payload(payload)
    publication_manifest = (
        private_authority[0]
        if private_authority is not None
        else manifest_from_authority(payload)
    )
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
    swarm_plan = _swarm_plan_from_payload(payload)
    if live_plan_hash is not None and swarm_plan is not None:
        raise ValueError("stored live authority mixes legacy and swarm formats")
    if swarm_plan is not None:
        legacy_values = (
            payload.get("live_allowed_routes"),
            payload.get("live_projected_max_cents"),
            payload.get("live_source_policy"),
            payload.get("live_dispatch_config_hash"),
            payload.get("live_max_input_bytes"),
        )
        if any(value not in (None, []) for value in legacy_values):
            raise ValueError("stored live authority mixes legacy and swarm formats")
        if swarm_plan.goals_count != len(goals):
            raise ValueError("swarm authority conflicts with job goals")
        if swarm_plan.gather_per_goal != fanout:
            raise ValueError("swarm authority conflicts with job fanout")
        if model_id is not None and model_id not in {
            route.split("/", 1)[1] for route in swarm_plan.role("synthesizer").allowed_routes
        }:
            raise ValueError("swarm authority conflicts with selected model")
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
        live_execution_plan_hash=(
            swarm_plan.plan_hash
            if swarm_plan is not None
            else None
            if live_plan is None
            else live_plan.plan_hash
        ),
        context_binding_sha256=(
            str(payload["context_binding_sha256"])
            if payload.get("context_binding_sha256") is not None
            else None
        ),
        publication_manifest_sha256=(
            publication_manifest.manifest_sha256
            if publication_manifest is not None
            else None
        ),
        publication_capability_sha256=(
            str(payload["publication_capability_sha256"])
            if payload.get("publication_capability_sha256") is not None
            else None
        ),
        publication_manifest_schema_version=(
            2 if private_authority is not None else None
        ),
        owner_private_publication_authority_sha256=(
            private_authority[1].authority_sha256
            if private_authority is not None
            else None
        ),
        private_output_policy_sha256=(
            private_authority[1].output_policy_sha256
            if private_authority is not None
            else None
        ),
    )


def _swarm_plan_from_payload(payload: Mapping[str, object]) -> SwarmLivePlan | None:
    plan_hash = payload.get("swarm_live_plan_hash")
    plan_json = payload.get("swarm_live_plan_json")
    if (plan_hash is None) != (plan_json is None):
        raise ValueError("stored swarm authority is incomplete")
    if plan_hash is None:
        return None
    if type(plan_hash) is not str or type(plan_json) is not str:
        raise ValueError("stored swarm authority has invalid types")
    plan = SwarmLivePlan.model_validate_json(plan_json)
    if plan.plan_hash != plan_hash:
        raise ValueError("stored swarm authority hash conflicts with its plan")
    return plan


def _require_publication_capability(
    deps: MidnightOilDependencies,
    row: OwnerJob,
    *,
    now_ms: int,
    required_until_ms: int,
) -> None:
    manifest = _require_publication_swarm_authority(row)
    if manifest is None or not manifest.sources:
        return
    capability_hash = row.payload.get("publication_capability_sha256")
    if type(capability_hash) is not str:
        raise ValueError("reviewed publication capability is not pinned")
    require_pinned_publication_capability(
        deps.publication_capabilities,
        capability_sha256=capability_hash,
        manifest=manifest,
        now_ms=now_ms,
        required_until_ms=required_until_ms,
    )


def _require_publication_swarm_authority(row: OwnerJob) -> Any:
    from substrate.midnight_oil.private_provider_authority import (
        owner_private_authority_from_payload,
    )
    from substrate.midnight_oil.publication_sources import manifest_from_authority

    private_authority = owner_private_authority_from_payload(row.payload)
    manifest = (
        private_authority[0]
        if private_authority is not None
        else manifest_from_authority(row.payload)
    )
    if manifest is not None and manifest.sources and _swarm_plan_from_payload(row.payload) is None:
        raise ValueError("reviewed publication execution requires signed swarm authority")
    return manifest


class _PublicationCapabilityUnavailable(ValueError):
    """The pinned reviewed-publication authority cannot cover this transition."""


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
    if row.operation_state is not OperationState.NONE:
        raise HTTPException(status_code=409, detail="job already has spend consent")
    try:
        from substrate.midnight_oil.private_provider_authority import (
            owner_private_authority_from_payload,
        )

        private_authority = owner_private_authority_from_payload(row.payload)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=409,
            detail="stored job configuration is invalid",
            headers={"Cache-Control": "no-store"},
        ) from None
    if private_authority is not None:
        from substrate.midnight_oil.private_provider_authority import (
            LivePrivateProviderAuthorityResolver,
            prospective_owner_private_queue_commitment_from_payload,
            recompute_owner_private_consent_config,
        )

        resolver = _private_authority_resolver(request)
        try:
            duration = row.payload.get("duration_minutes")
            now_ms = deps.clock_ms()
            if (
                not isinstance(resolver, LivePrivateProviderAuthorityResolver)
                or type(duration) is not int
                or isinstance(duration, bool)
            ):
                raise ValueError("owner-private live authority is unavailable")
            legacy_job = get_job(job_id, store=deps.jobs)
            if legacy_job is None:
                raise ValueError("owner-private job detail is unavailable")
            recompute_owner_private_consent_config(row, legacy_job).canonical_hash()
            prospective_owner_private_queue_commitment_from_payload(row.payload)
            live_authority = resolver.resolve(
                private_authority[0],
                now_ms=now_ms,
                required_until_ms=(
                    now_ms
                    + CONSENT_TTL_MS
                    + duration * 60_000
                    + deps.publication_completion_margin_ms
                ),
            )
            if not secrets.compare_digest(
                live_authority.authority_sha256,
                private_authority[1].authority_sha256,
            ):
                raise ValueError("owner-private live authority changed")
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail="owner-private execution remains disabled",
            headers={"Cache-Control": "no-store"},
        )
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
    try:
        swarm_plan = _swarm_plan_from_payload(row.payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored swarm authority is invalid") from exc
    if swarm_plan is not None and ceiling < swarm_plan.projected_total_cents:
        raise HTTPException(
            status_code=400,
            detail="ceiling cannot cover the signed live swarm topology",
        )

    try:
        operation_id = deps.random_token(24)
        nonce = deps.random_token(32)
        if (
            type(operation_id) is not str
            or not 16 <= len(operation_id) <= 512
            or type(nonce) is not str
            or not 16 <= len(nonce) <= 512
            or operation_id == nonce
        ):
            raise ValueError("invalid entropy source")
        if swarm_plan is not None and deps.consent_stage_coordinator is None:
            raise RuntimeError("swarm consent coordinator is unavailable")
        lock = (
            nullcontext()
            if deps.consent_stage_coordinator is None
            else deps.consent_stage_coordinator.acquire(job_id)
        )
        with lock:
            current = deps.owner_jobs.get_job(owner_user_id=owner, job_id=job_id)
            if current is None or current.state_version != row.state_version:
                raise ValueError("job changed before consent preparation")
            now = deps.clock_ms()
            if type(now) is not int or now < 0:
                raise ValueError("invalid clock")
            try:
                _require_publication_capability(
                    deps,
                    current,
                    now_ms=now,
                    required_until_ms=(
                        now
                        + CONSENT_TTL_MS
                        + config.duration_minutes * 60_000
                        + deps.publication_completion_margin_ms
                    ),
                )
            except ValueError as exc:
                raise _PublicationCapabilityUnavailable from exc
            stage_plan = (
                None
                if swarm_plan is None
                else build_stage_plan(
                    swarm_plan,
                    operation_id=operation_id,
                    job_id=job_id,
                    approved_ceiling_cents=ceiling,
                )
            )
            operation_config = replace(
                config,
                stage_plan_hash=None if stage_plan is None else stage_plan.plan_hash,
            )
            if stage_plan is not None:
                if not isinstance(deps.jobs, DurableJobStore):
                    raise RuntimeError("durable stage-plan store is unavailable")
                deps.jobs.prepare_stage_plan(stage_plan)
            token = deps.consents.issue(
                operator_id=owner,
                config=operation_config,
                operation_id=operation_id,
                ceiling_cents=ceiling,
                issued_at_ms=now,
                expires_at_ms=now + CONSENT_TTL_MS,
                nonce=nonce,
                key_id=deps.active_key_id,
                signing_key=deps.signing_key,
            )
            receipt: ConsentReceipt = decode_and_verify(
                token, verification_keys=deps.verification_keys
            )
            published = deps.owner_jobs.publish_consent(
                owner_user_id=owner,
                job_id=job_id,
                expected_version=row.state_version,
                operation_id=operation_id,
                approved_ceiling_cents=ceiling,
                consent_receipt_id=receipt.receipt_id,
                consent_config_hash=receipt.config_hash,
                consent_issued_at_ms=receipt.issued_at_ms,
                consent_expires_at_ms=receipt.expires_at_ms,
                consent_stage_plan_hash=(None if stage_plan is None else stage_plan.plan_hash),
            )
    except _PublicationCapabilityUnavailable:
        raise HTTPException(
            status_code=409,
            detail="reviewed publication capability is unavailable for consent",
            headers={"Cache-Control": "no-store"},
        ) from None
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
    }


@midnight_oil_router.delete("/jobs/{job_id}/spend-consent")
def delete_spend_consent(request: Request, job_id: str, response: Response) -> dict[str, object]:
    """Reset exact authority that has not crossed the delivery boundary.

    The operation queue lock arbitrates reset against enqueue.  The authority
    CAS then binds the reset to the exact version, operation, and receipt that
    the owner observed.  Either unclaimed ``CONSENT_ISSUED`` authority or
    claimed ``QUEUED`` authority with no active or terminal queue row may be
    reset.  Delivered, running, and terminal authority can never be reopened.
    """
    deps, authority = _owned(request, job_id)
    if deps.operation_queue is None:
        raise HTTPException(
            status_code=503,
            detail="durable operation queue is unavailable",
            headers={"Cache-Control": "no-store"},
        )
    if (
        authority.operation_state not in {OperationState.CONSENT_ISSUED, OperationState.QUEUED}
        or authority.operation_id is None
        or authority.consent_receipt_id is None
        or (
            authority.operation_state is OperationState.CONSENT_ISSUED
            and authority.consent_claimed_at_ms is not None
        )
        or (
            authority.operation_state is OperationState.QUEUED
            and authority.consent_claimed_at_ms is None
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="spend consent is not resettable",
            headers={"Cache-Control": "no-store"},
        )

    def reset_authority() -> Any:
        if authority.consent_stage_plan_hash is not None and deps.consent_stage_coordinator is None:
            raise RuntimeError("swarm consent coordinator is unavailable")
        lock = (
            nullcontext()
            if deps.consent_stage_coordinator is None
            else deps.consent_stage_coordinator.acquire(authority.job_id)
        )
        with lock:
            current = deps.owner_jobs.get_job(
                owner_user_id=authority.owner_user_id, job_id=authority.job_id
            )
            if current is None or current.state_version != authority.state_version:
                raise ValueError("consent authority changed before reset")
            return deps.owner_jobs.reset_undelivered_consent(
                owner_user_id=authority.owner_user_id,
                job_id=authority.job_id,
                expected_version=authority.state_version,
                expected_state=authority.operation_state,
                operation_id=authority.operation_id or "",
                consent_receipt_id=authority.consent_receipt_id or "",
            )

    try:
        reset = deps.operation_queue.run_if_undelivered(authority.operation_id, reset_authority)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="spend consent already crossed the delivery boundary",
            headers={"Cache-Control": "no-store"},
        ) from None
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="spend consent reset is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None
    if not reset.applied or reset.job is None:
        raise HTTPException(
            status_code=409,
            detail="spend consent changed during reset",
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "schema_version": 1,
        "job_id": reset.job.job_id,
        "state": "consent_required",
        "operation_state": reset.job.operation_state.value,
        "state_version": reset.job.state_version,
        "operator_action": "issue_consent",
    }


@midnight_oil_router.get("/jobs/{job_id}")
def get_job_route(request: Request, job_id: str) -> dict[str, Any]:
    deps, _ = _owned(request, job_id)
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "status": job.status,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "force_below_recommended": job.force_below_recommended,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "notes": job.notes,
        "view_format": "html",
        "runnable": False,
        "html": job_summary_html(job),
    }


@midnight_oil_router.get("/jobs/{job_id}/status")
def get_job_status_route(request: Request, job_id: str, response: Response) -> dict[str, object]:
    deps, authority = _owned(request, job_id)
    if deps.operation_queue is None:
        raise HTTPException(status_code=503, detail="durable operation queue is unavailable")
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        config = replace(_config(authority), stage_plan_hash=authority.consent_stage_plan_hash)
        if not _legacy_matches_authority(job, config):
            raise LifecycleIntegrityError("job detail conflicts with owner authority")
        budget_path = deps.jobs.budget_db_path()
        if not Path(budget_path).is_file():
            exposure = None
        else:
            try:
                exposure = BudgetLedger(budget_path).exposure(job.job_id)
            except ReservationNotFound:
                exposure = None
            except Exception as exc:
                raise LifecycleIntegrityError("budget exposure cannot be read") from exc
        status = project_lifecycle_status(
            authority=authority,
            job=job,
            operation_queue=deps.operation_queue,
            now_ms=deps.clock_ms(),
            budget_exposure=exposure,
        )
    except (KeyError, TypeError, ValueError, LifecycleIntegrityError):
        raise HTTPException(
            status_code=409,
            detail="job lifecycle requires reconciliation",
            headers={"Cache-Control": "no-store"},
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return status.to_dict()


@midnight_oil_router.get("/jobs/{job_id}/artifact", response_class=HTMLResponse)
def get_job_artifact_route(request: Request, job_id: str) -> HTMLResponse:
    deps, authority = _owned(request, job_id)
    if deps.engagement_store is None:
        raise HTTPException(status_code=503, detail="engagement store is unavailable")
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        config = _config(authority)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
    if not _legacy_matches_authority(job, config):
        raise HTTPException(status_code=409, detail="job configuration requires reconciliation")
    if authority.operation_state not in {
        OperationState.COMPLETE,
        OperationState.FAILED,
        OperationState.BUDGET_HALTED,
        OperationState.TIMED_OUT,
        OperationState.FAILED_RECONCILE,
    }:
        raise HTTPException(status_code=409, detail="HTML artifact is not terminal")
    if job.deposit_state != "complete" or not job.deposit_document_id:
        raise HTTPException(status_code=409, detail="HTML artifact is not deposited")
    document = deps.engagement_store.get_document(job.deposit_document_id)
    if document is None:
        raise HTTPException(status_code=409, detail="HTML artifact requires reconciliation")
    html_value = document.get("html")
    if (
        not isinstance(html_value, str)
        or len(html_value.encode("utf-8")) > 10_000_000
        or "<html" not in html_value.lower()
        or document.get("document_id") != job.deposit_document_id
        or document.get("job_id") != job.job_id
        or document.get("view_format") != "html"
        or job.deposit_html_sha256 is None
        or hashlib.sha256(html_value.encode("utf-8")).hexdigest() != job.deposit_html_sha256
    ):
        raise HTTPException(status_code=409, detail="HTML artifact requires reconciliation")
    return HTMLResponse(
        content=html_value,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


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
        config = replace(_config(authority), stage_plan_hash=authority.consent_stage_plan_hash)
        legacy = get_job(body.job_id, store=deps.jobs)
        if legacy is None:
            raise _run_error(404, "job not found")
        if (
            not _legacy_matches_authority(legacy, config)
            or config.canonical_hash() != authority.consent_config_hash
        ):
            raise _run_error(409, "job configuration requires reconciliation")
        _require_publication_capability(
            deps, authority, now_ms=now, required_until_ms=now
        )
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
    if current.operation_state is OperationState.NONE:
        # A concurrent owner reset won the authority CAS.  Never deliver the
        # now-revoked operation using the stale pre-reset snapshot.
        raise _run_error(409, "spend consent changed before enqueue")

    try:
        queued = deps.operation_queue.get(claim.receipt.operation_id)
    except Exception:
        raise _run_error(503, "operation queue is unavailable") from None
    if current.operation_state is OperationState.QUEUED and queued is None:
        expected_version = current.state_version
        expected_receipt_id = current.consent_receipt_id

        def require_current_queue_authority() -> None:
            latest_for_delivery = deps.owner_jobs.get_job(owner_user_id=owner, job_id=body.job_id)
            if (
                latest_for_delivery is None
                or latest_for_delivery.state_version != expected_version
                or latest_for_delivery.operation_state is not OperationState.QUEUED
                or latest_for_delivery.operation_id != claim.receipt.operation_id
                or latest_for_delivery.consent_receipt_id != expected_receipt_id
            ):
                raise ValueError("operation authority changed before delivery")
            delivery_now = deps.clock_ms()
            _require_publication_capability(
                deps,
                latest_for_delivery,
                now_ms=delivery_now,
                required_until_ms=delivery_now,
            )

        try:
            queued, _ = deps.operation_queue.enqueue_once_guarded(
                operation_id=claim.receipt.operation_id,
                owner_user_id=owner,
                job_id=body.job_id,
                enqueued_at_ms=now,
                options={
                    "max_steps": body.max_steps,
                    "auto_deposit": body.auto_deposit,
                    "draft_combined": body.draft_combined,
                    "force_offline": body.force_offline,
                },
                authority_guard=require_current_queue_authority,
            )
        except ValueError:
            raise _run_error(409, "operation queue conflicts with authority") from None
        except Exception:
            raise _run_error(503, "operation enqueue is unavailable") from None
    elif queued is not None and (queued.owner_user_id != owner or queued.job_id != body.job_id):
        raise _run_error(409, "operation queue conflicts with authority")
    return {
        "job_id": body.job_id,
        "operation_id": claim.receipt.operation_id,
        "state": current.operation_state.value,
    }


@midnight_oil_router.post("/deposit")
def post_deposit(request: Request, body: DepositBody) -> dict[str, Any]:
    from interfaces.research.api.engagement_routes import get_bench_usage_store
    from substrate.engagement_spine import progress_payload

    deps, authority = _owned(request, body.job_id)
    if deps.engagement_store is None:
        raise HTTPException(status_code=503, detail="engagement store is unavailable")
    terminal = {
        OperationState.COMPLETE,
        OperationState.FAILED,
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
            engagement_store=deps.engagement_store,
            job_snapshot=job,
            draft_combined=body.draft_combined,
            bench_usage_store=get_bench_usage_store(create_if_missing=True),
            record_progress=body.record_progress,
            owner_id=authority.owner_user_id,
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
                store=deps.engagement_store,
                include_html=body.include_progress_html,
                owner_id=authority.owner_user_id,
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


@midnight_oil_router.get("/jobs/{job_id}/twins")
def get_job_twins_route(request: Request, job_id: str) -> dict[str, Any]:
    from substrate.engagement_spine import twins_product_payload

    deps, authority = _owned(request, job_id)
    if deps.engagement_store is None:
        raise HTTPException(status_code=503, detail="engagement store is unavailable")
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        config = _config(authority)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
    if not _legacy_matches_authority(job, config) or not job.asset_id:
        raise HTTPException(status_code=409, detail="job configuration requires reconciliation")
    return twins_product_payload(
        job.asset_id,
        store=deps.engagement_store,
        include_html=True,
        owner_id=authority.owner_user_id,
    )


@midnight_oil_router.get("/live-step-status")
def get_live_step_status(request: Request) -> dict[str, Any]:
    _owner(request)
    from substrate.midnight_oil import live_step_status_payload

    return live_step_status_payload()


def register_midnight_oil_routes(
    app: FastAPI,
    *,
    dependencies: MidnightOilDependencies | None = None,
    private_authority_resolver: object | None = None,
) -> None:
    if dependencies is None:
        raise RuntimeError("Midnight Oil durable dependencies must be configured at startup")
    setattr(app.state, _DEPENDENCIES, dependencies)
    if private_authority_resolver is not None:
        from substrate.midnight_oil.private_provider_authority import (
            LivePrivateProviderAuthorityResolver,
        )

        if not isinstance(private_authority_resolver, LivePrivateProviderAuthorityResolver):
            raise TypeError("private authority resolver is invalid")
        setattr(app.state, _PRIVATE_AUTHORITY_RESOLVER, private_authority_resolver)
    app.include_router(midnight_oil_router)


__all__ = [
    "MidnightOilDependencies",
    "midnight_oil_preflight_router",
    "midnight_oil_router",
    "post_midnight_oil_preflight",
    "post_midnight_oil_execute",
    "register_midnight_oil_routes",
]
