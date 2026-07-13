"""Durable Midnight Oil worker process and ``antiek midnight-oil-worker`` CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol, cast

from substrate.dispatch import DispatchConfig
from substrate.graph.retrieval_substrate import RetrievalSubstrate, make_substrate
from substrate.graph.search import EmbeddingModel, SentenceTransformerEmbedding

from .budget_ledger import BudgetLedger
from .job import TerminalReason, get_job, put_job_state
from .job_store import OperationState
from .live import (
    LiveExecutionFailed,
    RouterIdempotentDispatch,
    live_plan_from_authority,
    resume_terminal_deposit,
    resume_terminal_projection,
    run_authorized_live_iteration,
)
from .live_roles import (
    CanonicalSourceReceipt,
    PlannerOutput,
    parse_role_output,
    publication_source_receipt_id,
)
from .live_stage_engine import LiveSwarmStageEngine, RouterStageDispatch
from .private_provider_authority import (
    LivePrivateProviderAuthorityResolver,
    owner_private_authority_from_payload,
    prospective_owner_private_queue_commitment_from_payload,
    recompute_owner_private_consent_config,
)
from .private_provider_composition import (
    InvalidPrivateProviderRevocationStore,
    PrivateProviderComposition,
    build_private_provider_composition,
)
from .publication_capability import (
    PublicationCapabilityRegistry,
    require_pinned_publication_capability,
)
from .publication_sources import (
    AcquiredPublicationExcerpt,
    PublicationAcquirer,
    ReviewedPublicationSource,
    acquire_reviewed_publications_durably,
    manifest_from_authority,
)
from .runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeConfigError,
    MidnightOilRuntimeStores,
    build_runtime_stores,
    install_attested_providers,
    load_consent_keyring,
    provider_api_key_inventory,
)
from .session_flywheel import finalize_bound_session, validate_context_binding
from .spend_consent import JobConsentConfig
from .swarm_plan import RouterSwarmDispatch, SwarmLivePlan, swarm_plan_from_authority
from .worker import WorkerLease, lease_authorized_operation

WorkerResult = Literal[
    "no_work",
    "complete",
    "recovered",
    "contended",
    "failed",
    "failed_reconcile",
    "blocked_provider",
    "reconcile_required",
    "deposit_pending",
    "projection_pending",
    "lease_pending",
    "budget_halted",
    "timed_out",
]


class _SwarmStageFailed(LiveExecutionFailed):
    def __init__(self, outcome: str) -> None:
        super().__init__()
        self.outcome = outcome

    @property
    def reconcile(self) -> bool:
        return self.outcome == "unknown"


class _ClosableRetrieval(RetrievalSubstrate, Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class WorkerPhaseRecord:
    result: WorkerResult
    phase: str
    worker_id: str
    operation_id: str | None = None
    job_id: str | None = None
    lease_generation: int | None = None
    deposit_document_id: str | None = None
    graph_deliverable_id: str | None = None
    graph_html_sha256: str | None = None
    error_code: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class MidnightOilWorkerRuntime:
    config: MidnightOilRuntimeConfig
    stores: MidnightOilRuntimeStores
    dispatch_config: DispatchConfig
    publication_acquirer: PublicationAcquirer | None = None
    publication_capabilities: PublicationCapabilityRegistry = field(
        default_factory=PublicationCapabilityRegistry
    )
    publication_acquirers: Mapping[str, PublicationAcquirer] = field(default_factory=dict)
    private_provider_composition: PrivateProviderComposition | None = None


def _guard_owner_private_authority(
    runtime: MidnightOilWorkerRuntime, authority: object, now_ms: int
) -> None:
    from .job_store import OwnerJob

    if not isinstance(authority, OwnerJob):
        raise ValueError("owner-private authority is invalid")
    private_authority = owner_private_authority_from_payload(authority.payload)
    if private_authority is None:
        return
    job = get_job(authority.job_id, store=runtime.stores.jobs)
    duration = authority.payload.get("duration_minutes")
    if (
        job is None
        or runtime.private_provider_composition is None
        or type(duration) is not int
        or isinstance(duration, bool)
    ):
        raise ValueError("owner-private live authority is unavailable")
    stage_plan_hash = None
    if authority.operation_state is not OperationState.NONE:
        if (
            authority.consent_stage_plan_hash is None
            or authority.consent_config_hash is None
        ):
            raise ValueError("owner-private queued consent authority is incomplete")
        stage_plan = runtime.stores.jobs.get_stage_plan(authority.job_id)
        if (
            stage_plan.plan_hash != authority.consent_stage_plan_hash
            or stage_plan.operation_id != authority.operation_id
        ):
            raise ValueError("owner-private stage plan requires reconciliation")
        stage_plan_hash = stage_plan.plan_hash
    config_hash = recompute_owner_private_consent_config(
        authority,
        job,
        stage_plan_hash=stage_plan_hash,
    ).canonical_hash()
    if (
        authority.consent_config_hash is not None
        and config_hash != authority.consent_config_hash
    ):
        raise ValueError("owner-private consent configuration requires reconciliation")
    prospective_owner_private_queue_commitment_from_payload(authority.payload)
    current = LivePrivateProviderAuthorityResolver(
        runtime.private_provider_composition
    ).resolve(
        private_authority[0],
        now_ms=now_ms,
        required_until_ms=(
            now_ms + duration * 60_000 + runtime.config.worker_lease_ms
        ),
    )
    if current.authority_sha256 != private_authority[1].authority_sha256:
        raise ValueError("owner-private live authority changed")
    raise ValueError("owner-private execution remains disabled")


_SWARM_VALIDATOR_SHA256 = hashlib.sha256(b"antiek.midnight-oil.live-swarm-validator.v1").hexdigest()


def _validated_swarm_runtime(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    authority: object,
) -> tuple[SwarmLivePlan, RouterStageDispatch, BudgetLedger]:
    from .job_store import OwnerJob

    if not isinstance(authority, OwnerJob):
        raise TypeError("swarm execution requires owner authority")
    swarm = swarm_plan_from_authority(authority)
    if (
        authority.operation_id != lease.operation_id
        or authority.approved_ceiling_cents is None
        or authority.consent_stage_plan_hash is None
        or authority.consent_config_hash is None
    ):
        raise ValueError("swarm execution lacks complete operation authority")
    plan = runtime.stores.jobs.get_stage_plan(lease.job_id)
    if (
        plan.job_id != lease.job_id
        or plan.operation_id != lease.operation_id
        or plan.approved_ceiling_cents != authority.approved_ceiling_cents
        or plan.plan_hash != authority.consent_stage_plan_hash
    ):
        raise ValueError("durable stage plan conflicts with owner consent authority")
    job = get_job(lease.job_id, store=runtime.stores.jobs)
    if job is None:
        raise ValueError("swarm execution lacks job details")
    validate_context_binding(authority, job)
    signed = JobConsentConfig(
        job_id=job.job_id,
        goals=job.goals,
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
        asset_id=job.asset_id,
        live_execution_plan_hash=swarm.plan_hash,
        stage_plan_hash=plan.plan_hash,
        context_binding_sha256=(
            str(authority.payload["context_binding_sha256"])
            if authority.payload.get("context_binding_sha256") is not None
            else None
        ),
        publication_manifest_sha256=(
            str(authority.payload["publication_manifest_sha256"])
            if authority.payload.get("publication_manifest_sha256") is not None
            else None
        ),
        publication_capability_sha256=(
            str(authority.payload["publication_capability_sha256"])
            if authority.payload.get("publication_capability_sha256") is not None
            else None
        ),
    )
    if owner_private_authority_from_payload(authority.payload) is not None:
        signed = recompute_owner_private_consent_config(
            authority,
            job,
            stage_plan_hash=plan.plan_hash,
        )
    if signed.canonical_hash() != authority.consent_config_hash:
        raise ValueError("stage plan conflicts with signed consent configuration")
    router = RouterSwarmDispatch(plan=swarm, config=runtime.dispatch_config)
    dispatch = RouterStageDispatch(
        router=router,
        role_plan_hashes={role.role: role.plan_hash for role in swarm.roles},
    )
    ledger = BudgetLedger(runtime.stores.jobs.budget_db_path())
    ledger.ensure_schema()
    role_budgets: dict[str, int] = {
        role.role: sum(
            stage.projected_max_cents for stage in plan.stages if stage.router_role == role.role
        )
        for role in swarm.roles
    }
    ledger.reserve(lease.job_id, plan.approved_ceiling_cents, role_budgets)
    return swarm, dispatch, ledger


def _gather_input(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    retrieval: RetrievalSubstrate,
    publication_excerpts: tuple[AcquiredPublicationExcerpt, ...] = (),
) -> tuple[dict[str, object], tuple[CanonicalSourceReceipt, ...]]:
    plan = runtime.stores.jobs.get_stage_plan(lease.job_id)
    queued = runtime.stores.operation_queue.get(lease.operation_id)
    if queued is None or queued.next_step_index >= len(plan.stages):
        raise ValueError("swarm cursor is outside durable stage plan")
    item = plan.stages[queued.next_step_index]
    if item.kind != "gather" or item.shard_index is None:
        return {}, ()
    planner = next(
        row for row in plan.stages if row.goal_index == item.goal_index and row.kind == "planner"
    )
    checkpoint = runtime.stores.jobs.get_stage_effect(lease.job_id, planner.stage_key)
    if checkpoint is None:
        raise ValueError("gather stage lacks durable planner output")
    output = parse_role_output(str(checkpoint[1]["output_text"]))
    if not isinstance(output, PlannerOutput):
        raise ValueError("gather predecessor is not a planner output")
    question = output.questions[item.shard_index]
    result = retrieval.query(question.question, top_k=12, policy_tag="private_research")
    rows = result.get("results")
    if not isinstance(rows, list):
        raise ValueError("retrieval substrate returned invalid gather results")
    excerpts: list[dict[str, str]] = []
    receipts: list[CanonicalSourceReceipt] = []
    for row in rows[: max(0, 100 - len(publication_excerpts))]:
        if not isinstance(row, dict):
            raise ValueError("retrieval result is outside gather contract")
        document_id = str(row.get("document_id") or "").strip()
        chunk_id = str(row.get("chunk_id") or "").strip()
        text = str(row.get("chunk_text") or "")
        if not document_id or not chunk_id or len(text.encode()) > 100_000:
            raise ValueError("retrieval result lacks bounded canonical provenance")
        excerpt_sha = hashlib.sha256(text.encode()).hexdigest()
        receipt_id = hashlib.sha256(
            b"antiek.midnight-oil.source-receipt.v1\x00"
            + f"{question.question_id}\x00{document_id}\x00{chunk_id}\x00{excerpt_sha}".encode()
        ).hexdigest()
        receipts.append(
            CanonicalSourceReceipt(
                source_receipt_id=receipt_id,
                question_id=question.question_id,
                document_id=document_id,
                chunk_id=chunk_id,
                excerpt_sha256=excerpt_sha,
            )
        )
        excerpts.append({"source_receipt_id": receipt_id, "text": text})
    authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if authority is None:
        raise ValueError("publication gather lost owner authority")
    manifest = manifest_from_authority(authority.payload)
    allowed_refs = set() if manifest is None else {source.ref_id for source in manifest.sources}
    execution_id = authority.payload.get("execution_id")
    capability_hash = authority.payload.get("publication_capability_sha256")
    if publication_excerpts and (type(execution_id) is not str or not execution_id):
        raise ValueError("publication gather lacks execution scope")
    if publication_excerpts and type(capability_hash) is not str:
        raise ValueError("publication gather lacks connector capability scope")
    owner_scope_sha256 = hashlib.sha256(
        b"antiek.midnight-oil.owner-scope.v1\x00" + lease.owner_user_id.encode()
    ).hexdigest()
    for publication in publication_excerpts:
        if publication.ref_id not in allowed_refs or manifest is None:
            raise ValueError("publication excerpt is outside owner authority")
        receipt_id = publication_source_receipt_id(
            owner_scope_sha256=owner_scope_sha256,
            execution_id=str(execution_id),
            job_id=lease.job_id,
            stage_key=item.stage_key,
            router_role="gatherer",
            route_plan_sha256=item.route_plan_sha256,
            question_id=question.question_id,
            publication_manifest_sha256=manifest.manifest_sha256,
            publication_capability_sha256=str(capability_hash),
            reviewed_ref_id=publication.ref_id,
            excerpt_sha256=publication.excerpt_sha256,
        )
        receipts.append(
            CanonicalSourceReceipt(
                source_receipt_id=receipt_id,
                question_id=question.question_id,
                document_id=publication.ref_id,
                chunk_id=f"{publication.connector}:{publication.external_id}"[:512],
                excerpt_sha256=publication.excerpt_sha256,
                source_type="publication",
                publication_manifest_sha256=manifest.manifest_sha256,
                publication_capability_sha256=str(capability_hash),
                reviewed_ref_id=publication.ref_id,
                connector=publication.connector,
                canonical_url=publication.canonical_url,
                acquisition_mode=publication.acquisition_mode,
                rights_use=publication.rights_use,
                rights_tier=publication.rights_tier,
                truncated=publication.truncated,
                excerpt_bytes=publication.excerpt_bytes,
                owner_scope_sha256=owner_scope_sha256,
                execution_id=str(execution_id),
                job_id=lease.job_id,
                stage_key=item.stage_key,
                router_role="gatherer",
                route_plan_sha256=item.route_plan_sha256,
                connector_version=publication.connector_version,
                extraction_mode=publication.extraction_mode,
                truncation_reason=publication.truncation_reason,
                source_length=publication.source_length,
            )
        )
        excerpts.append({"source_receipt_id": receipt_id, "text": publication.text})
    return {"excerpts": excerpts}, tuple(receipts)


def _run_swarm_operation(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    authority: object,
    retrieval: RetrievalSubstrate,
    *,
    clock_ms: Callable[[], int],
) -> tuple[str, bool]:
    _, dispatch, ledger = _validated_swarm_runtime(runtime, lease, authority)
    from .job_store import OwnerJob

    if not isinstance(authority, OwnerJob):
        raise TypeError("swarm execution requires owner authority")
    manifest = manifest_from_authority(authority.payload)
    publication_excerpts: tuple[AcquiredPublicationExcerpt, ...] = ()
    if manifest is not None and manifest.sources:
        capability_hash = authority.payload.get("publication_capability_sha256")
        if type(capability_hash) is not str:
            raise ValueError("reviewed publication capability is not pinned")
        capability = runtime.publication_capabilities.get(capability_hash)
        if capability is None:
            raise ValueError("reviewed publication capability is not configured")
        acquirer = runtime.publication_acquirers.get(capability_hash)
        if acquirer is None:
            acquirer = runtime.publication_acquirer
        if acquirer is None:
            raise ValueError("reviewed publication connector is not configured")

        def revalidate_before_transport() -> None:
            now = clock_ms()
            require_pinned_publication_capability(
                runtime.publication_capabilities,
                capability_sha256=capability_hash,
                manifest=manifest,
                now_ms=now,
                required_until_ms=now,
            )

        def acquire_with_current_capability(
            source: ReviewedPublicationSource,
        ) -> AcquiredPublicationExcerpt:
            revalidate_before_transport()
            from acquisition.arxiv.midnight_oil import ArxivAbstractPublicationAcquirer

            if isinstance(acquirer, ArxivAbstractPublicationAcquirer):
                return acquirer(source, before_transport=revalidate_before_transport)
            return acquirer(source)

        publication_excerpts = acquire_reviewed_publications_durably(
            manifest,
            owner_id=lease.owner_user_id,
            job_id=lease.job_id,
            store=runtime.stores.engagement_store,
            acquire=acquire_with_current_capability,
            publication_capability_sha256=capability_hash,
            expected_connector_version=capability.connector_version,
            before_transport=revalidate_before_transport,
        )
    plan = runtime.stores.jobs.get_stage_plan(lease.job_id)
    engine = LiveSwarmStageEngine(
        job_id=lease.job_id,
        operation_id=lease.operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        store=runtime.stores.jobs,
        ledger=ledger,
        operation_queue=runtime.stores.operation_queue,
        dispatch=dispatch,
        now_ms=clock_ms,
        validator_sha256=_SWARM_VALIDATOR_SHA256,
    )
    queued = runtime.stores.operation_queue.get(lease.operation_id)
    if queued is None or queued.next_step_index >= len(plan.stages):
        raise ValueError("swarm operation cursor is outside its stage plan")
    item = plan.stages[queued.next_step_index]
    if item.kind == "gather":
        payload, receipts = _gather_input(
            runtime, lease, retrieval, publication_excerpts
        )
    elif item.kind == "planner":
        payload = {
            "publication_inventory": [
                {
                    "ref_id": row.ref_id,
                    "kind": row.kind,
                    "excerpt_sha256": row.excerpt_sha256,
                    "excerpt_bytes": row.excerpt_bytes,
                }
                for row in publication_excerpts
            ]
        }
        receipts = ()
    else:
        payload, receipts = {}, ()
    result = engine.run_current_stage(stage_payload=payload, source_receipts=receipts)
    _renew(runtime, lease, clock_ms=clock_ms)
    if result.outcome != "settled":
        raise _SwarmStageFailed(result.outcome)
    advanced = runtime.stores.operation_queue.get(lease.operation_id)
    if advanced is None:
        raise ValueError("swarm operation disappeared after stage settlement")
    max_steps = advanced.options.get("max_steps")
    if (
        type(max_steps) is int
        and advanced.next_step_index >= max_steps
        and advanced.next_step_index < len(plan.stages)
    ):
        raise _SwarmStageFailed("max_steps")
    if advanced.next_step_index < len(plan.stages):
        return result.outcome, False
    job = get_job(lease.job_id, store=runtime.stores.jobs)
    if job is None:
        raise ValueError("swarm completion lost job details")
    balance = ledger.balance(lease.job_id)
    put_job_state(
        replace(job, status="complete", spent_usd=balance.spent_cents / 100),
        store=runtime.stores.jobs,
    )
    current = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if current is None or current.operation_state is not OperationState.RUNNING:
        raise ValueError("swarm completion lost running owner authority")
    changed = runtime.stores.owner_jobs.compare_and_set(
        owner_user_id=lease.owner_user_id,
        job_id=lease.job_id,
        expected_version=current.state_version,
        expected_state=OperationState.RUNNING,
        operation_id=lease.operation_id,
        next_state=OperationState.COMPLETE,
        completed_at_ms=clock_ms(),
    )
    if not changed.applied:
        raise ValueError("swarm completion lost owner compare-and-set")
    return result.outcome, True


def build_worker_runtime(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> MidnightOilWorkerRuntime:
    environment = os.environ if environ is None else environ
    config = MidnightOilRuntimeConfig.from_file(config_path)
    _, verification_keys = load_consent_keyring(config, environment)
    stores = build_runtime_stores(config)
    provider_key_envs, provider_key_values = provider_api_key_inventory(
        config, environment
    )
    try:
        private_provider_composition = build_private_provider_composition(
            state_dir=config.state_dir,
            environ=environment,
            now_ms=time.time_ns() // 1_000_000,
            forbidden_key_envs=frozenset(
                config.consent_verification_key_envs.values()
            )
            | provider_key_envs,
            forbidden_keys=tuple(verification_keys.values()),
            forbidden_key_values=provider_key_values,
        )
    except (ValueError, InvalidPrivateProviderRevocationStore, sqlite3.Error, OSError):
        raise MidnightOilRuntimeConfigError(
            "Private provider composition is invalid"
        ) from None
    install_attested_providers(config, environment)
    publication_capabilities = PublicationCapabilityRegistry.from_paths(
        config.publication_capability_paths,
        verification_keys=verification_keys,
    )
    from acquisition.arxiv.midnight_oil import (
        ArxivAbstractPublicationAcquirer,
        FileDestinationAudit,
    )

    publication_acquirers: dict[str, PublicationAcquirer] = {
        capability_hash: ArxivAbstractPublicationAcquirer(
            capability,
            audit=FileDestinationAudit(config.state_dir / "publication-destinations.jsonl"),
        )
        for capability_hash in publication_capabilities.hashes
        if (capability := publication_capabilities.get(capability_hash)) is not None
    }
    return MidnightOilWorkerRuntime(
        config=config,
        stores=stores,
        dispatch_config=DispatchConfig.from_yaml(config.dispatch_config_path),
        publication_capabilities=publication_capabilities,
        publication_acquirers=publication_acquirers,
        private_provider_composition=private_provider_composition,
    )


def _terminal_state(state: OperationState) -> str:
    mapping = {
        OperationState.COMPLETE: "complete",
        OperationState.FAILED: "failed",
        OperationState.BUDGET_HALTED: "budget_halted",
        OperationState.TIMED_OUT: "timed_out",
        OperationState.FAILED_RECONCILE: "failed_reconcile",
    }
    try:
        return mapping[state]
    except KeyError as exc:
        raise ValueError("operation authority is not terminal") from exc


def _renew(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    *,
    clock_ms: Callable[[], int],
) -> None:
    now = clock_ms()
    if not runtime.stores.operation_queue.renew_lease(
        operation_id=lease.operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        renewed_at_ms=now,
        lease_expires_at_ms=now + runtime.config.worker_lease_ms,
    ):
        raise RuntimeError("worker phase lost its lease generation")


def _mark_failed_before_network(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    *,
    clock_ms: Callable[[], int],
    reconcile: bool,
    reason: TerminalReason,
) -> OperationState:
    authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    target = OperationState.FAILED_RECONCILE if reconcile else OperationState.FAILED
    if authority is None or authority.operation_id != lease.operation_id:
        raise RuntimeError("failure disposition lost owner authority")
    if authority.operation_state is OperationState.RUNNING:
        changed = runtime.stores.owner_jobs.compare_and_set(
            owner_user_id=lease.owner_user_id,
            job_id=lease.job_id,
            expected_version=authority.state_version,
            expected_state=OperationState.RUNNING,
            operation_id=lease.operation_id,
            next_state=target,
            completed_at_ms=clock_ms(),
        )
        if not changed.applied:
            raise RuntimeError("failure disposition lost authority compare-and-set")
    job = get_job(lease.job_id, store=runtime.stores.jobs)
    if job is not None:
        terminal_status = job.status in {
            "complete",
            "timed_out",
            "budget_halted",
            "failed",
        }
        effective_reason = (
            None
            if authority.operation_state
            in {
                OperationState.COMPLETE,
                OperationState.BUDGET_HALTED,
                OperationState.TIMED_OUT,
            }
            else reason
        )
        put_job_state(
            replace(
                job,
                status=job.status if terminal_status else "failed",
                terminal_reason=effective_reason,
            ),
            store=runtime.stores.jobs,
        )
    return target


def _archive_current_lease(
    runtime: MidnightOilWorkerRuntime,
    lease: WorkerLease,
    *,
    terminal_state: OperationState,
    clock_ms: Callable[[], int],
) -> None:
    if not runtime.stores.operation_queue.acknowledge_terminal(
        operation_id=lease.operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        terminal_state=_terminal_state(terminal_state),
        completed_at_ms=clock_ms(),
    ):
        raise RuntimeError("terminal disposition lost its queue fence")


def _recover_terminal(
    runtime: MidnightOilWorkerRuntime,
    *,
    operation_id: str,
    owner_user_id: str,
    job_id: str,
    worker_id: str,
    now_ms: int,
    clock_ms: Callable[[], int],
) -> WorkerPhaseRecord:
    queue = runtime.stores.operation_queue
    try:
        leased, won = queue.lease(
            operation_id=operation_id,
            worker_id=worker_id,
            leased_at_ms=now_ms,
            lease_expires_at_ms=now_ms + runtime.config.worker_lease_ms,
        )
    except KeyError:
        # Another worker may archive the terminal operation after this worker's
        # claimable read but before the per-operation lease lock is acquired.
        return WorkerPhaseRecord(
            result="contended",
            phase="terminal_recovery_claim",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
        )
    if not won:
        return WorkerPhaseRecord(
            result="contended",
            phase="terminal_recovery_claim",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
        )
    authority = runtime.stores.owner_jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
    if authority is None or authority.operation_id != operation_id:
        raise ValueError("terminal recovery lacks matching owner authority")
    deposit = resume_terminal_deposit(
        job_id,
        store=runtime.stores.jobs,
        engagement_store=runtime.stores.engagement_store,
        owner_user_id=owner_user_id,
    )
    recovered_job = get_job(job_id, store=runtime.stores.jobs)
    if recovered_job is None:
        raise RuntimeError("terminal recovery lost job details")
    finalize_bound_session(
        authority=authority,
        job=recovered_job,
        engagement_store=runtime.stores.engagement_store,
        session_store=runtime.stores.session_store,
    )
    recovery_lease = WorkerLease(
        operation_id=operation_id,
        owner_user_id=owner_user_id,
        job_id=job_id,
        worker_id=worker_id,
        step_index=leased.next_step_index,
        lease_generation=leased.lease_generation,
    )
    _renew(runtime, recovery_lease, clock_ms=clock_ms)
    job = get_job(job_id, store=runtime.stores.jobs)
    if job is None:
        raise RuntimeError("terminal recovery lost job details")
    graph = (
        resume_terminal_projection(
            job_id,
            owner_user_id=owner_user_id,
            owner_jobs=runtime.stores.owner_jobs,
            store=runtime.stores.jobs,
            engagement_store=runtime.stores.engagement_store,
            graph_db_path=runtime.config.graph_db_path,
        )
        if job.step_evidence
        else None
    )
    _renew(runtime, recovery_lease, clock_ms=clock_ms)
    if not queue.acknowledge_terminal(
        operation_id=operation_id,
        worker_id=worker_id,
        lease_generation=leased.lease_generation,
        terminal_state=_terminal_state(authority.operation_state),
        completed_at_ms=clock_ms(),
    ):
        raise RuntimeError("terminal recovery lost its queue fence")
    result_by_state: dict[OperationState, WorkerResult] = {
        OperationState.COMPLETE: "recovered",
        OperationState.FAILED: "failed",
        OperationState.BUDGET_HALTED: "budget_halted",
        OperationState.TIMED_OUT: "timed_out",
        OperationState.FAILED_RECONCILE: "reconcile_required",
    }
    return WorkerPhaseRecord(
        result=result_by_state[authority.operation_state],
        phase="terminal_archived",
        worker_id=worker_id,
        operation_id=operation_id,
        job_id=job_id,
        lease_generation=leased.lease_generation,
        deposit_document_id=deposit.document_id,
        graph_deliverable_id=(None if graph is None else graph.receipt.deliverable_id),
        graph_html_sha256=(None if graph is None else graph.receipt.html_sha256),
    )


def run_worker_once(
    runtime: MidnightOilWorkerRuntime,
    *,
    worker_id: str,
    embedding_model: EmbeddingModel,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    stop_requested: Callable[[], bool] = lambda: False,
) -> WorkerPhaseRecord:
    if not worker_id.strip() or len(worker_id) > 256:
        raise ValueError("worker id must be a bounded non-empty string")
    if stop_requested():
        return WorkerPhaseRecord(
            result="no_work", phase="shutdown_before_claim", worker_id=worker_id
        )
    now_ms = clock_ms()
    queued = runtime.stores.operation_queue.next_claimable(now_ms=now_ms)
    if queued is None:
        return WorkerPhaseRecord(result="no_work", phase="queue_empty", worker_id=worker_id)
    authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=queued.owner_user_id, job_id=queued.job_id
    )
    if authority is not None:
        try:
            _guard_owner_private_authority(runtime, authority, now_ms)
        except Exception:
            return WorkerPhaseRecord(
                result="contended",
                phase="private_authority_denied",
                worker_id=worker_id,
                operation_id=queued.operation_id,
                job_id=queued.job_id,
                error_code="configuration_blocked",
            )
    if authority is None or authority.operation_id != queued.operation_id:
        leased, won = runtime.stores.operation_queue.lease(
            operation_id=queued.operation_id,
            worker_id=worker_id,
            leased_at_ms=now_ms,
            lease_expires_at_ms=now_ms + runtime.config.worker_lease_ms,
        )
        if won:
            won = runtime.stores.operation_queue.acknowledge_terminal(
                operation_id=leased.operation_id,
                worker_id=worker_id,
                lease_generation=leased.lease_generation,
                terminal_state="failed_reconcile",
                completed_at_ms=now_ms,
            )
        return WorkerPhaseRecord(
            result="reconcile_required" if won else "contended",
            phase="authority_quarantined" if won else "authority_quarantine_contended",
            worker_id=worker_id,
            operation_id=queued.operation_id,
            job_id=queued.job_id,
            error_code="authority_mismatch",
        )
    if authority.operation_state in {
        OperationState.COMPLETE,
        OperationState.FAILED,
        OperationState.BUDGET_HALTED,
        OperationState.TIMED_OUT,
        OperationState.FAILED_RECONCILE,
    }:
        return _recover_terminal(
            runtime,
            operation_id=queued.operation_id,
            owner_user_id=queued.owner_user_id,
            job_id=queued.job_id,
            worker_id=worker_id,
            now_ms=now_ms,
            clock_ms=clock_ms,
        )
    try:
        def private_authority_guard(authority: object, guard_now_ms: int) -> None:
            try:
                _guard_owner_private_authority(runtime, authority, guard_now_ms)
            except Exception:
                raise ValueError("owner-private live authority is unavailable") from None

        lease = lease_authorized_operation(
            operation_id=queued.operation_id,
            owner_user_id=queued.owner_user_id,
            job_id=queued.job_id,
            owner_jobs=runtime.stores.owner_jobs,
            operation_queue=runtime.stores.operation_queue,
            jobs=runtime.stores.jobs,
            worker_id=worker_id,
            now_ms=now_ms,
            lease_expires_at_ms=now_ms + runtime.config.worker_lease_ms,
            private_authority_guard=private_authority_guard,
        )
    except ValueError:
        return WorkerPhaseRecord(
            result="contended",
            phase="lease_not_acquired",
            worker_id=worker_id,
            operation_id=queued.operation_id,
            job_id=queued.job_id,
        )
    running_authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if running_authority is None:
        raise RuntimeError("leased operation lost owner authority")
    try:
        is_swarm = running_authority.payload.get("swarm_live_plan_hash") is not None
        running_manifest = manifest_from_authority(running_authority.payload)
        if running_manifest is not None and running_manifest.sources and not is_swarm:
            raise ValueError("reviewed publication execution requires signed swarm authority")
        if is_swarm:
            # Verify every owner/consent/plan/router seam before constructing
            # a retrieval substrate or allowing a provider transport.
            _validated_swarm_runtime(runtime, lease, running_authority)
            dispatch = None
        else:
            plan = live_plan_from_authority(running_authority)
            dispatch = RouterIdempotentDispatch(plan=plan, config=runtime.dispatch_config)
        retrieval = cast(
            _ClosableRetrieval,
            make_substrate(
                runtime.config.retrieval_kind,
                str(runtime.config.graph_db_path),
                model=embedding_model,
            ),
        )
    except Exception:
        target = _mark_failed_before_network(
            runtime,
            lease,
            clock_ms=clock_ms,
            reconcile=False,
            reason="configuration_blocked",
        )
        try:
            deposit = resume_terminal_deposit(
                lease.job_id,
                store=runtime.stores.jobs,
                engagement_store=runtime.stores.engagement_store,
                owner_user_id=lease.owner_user_id,
            )
        except Exception:
            return WorkerPhaseRecord(
                result="deposit_pending",
                phase="blocked_provider_deposit_pending",
                worker_id=worker_id,
                operation_id=lease.operation_id,
                job_id=lease.job_id,
                lease_generation=lease.lease_generation,
                error_code="configuration_blocked",
            )
        _archive_current_lease(runtime, lease, terminal_state=target, clock_ms=clock_ms)
        return WorkerPhaseRecord(
            result="blocked_provider",
            phase="configuration_archived",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            deposit_document_id=deposit.document_id,
            error_code="configuration_blocked",
        )

    if stop_requested():
        retrieval.close()
        return WorkerPhaseRecord(
            result="lease_pending",
            phase="shutdown_before_provider",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
        )

    swarm_run: tuple[str, bool] | None = None
    try:
        try:
            if is_swarm:
                swarm_run = _run_swarm_operation(
                    runtime,
                    lease,
                    running_authority,
                    retrieval,
                    clock_ms=clock_ms,
                )
            else:
                if dispatch is None:
                    raise RuntimeError("legacy execution lacks router dispatch")
                run_authorized_live_iteration(
                    lease,
                    operation_queue=runtime.stores.operation_queue,
                    owner_jobs=runtime.stores.owner_jobs,
                    store=runtime.stores.jobs,
                    retrieval=retrieval,
                    dispatch=dispatch,
                    clock=_SystemClock(clock_ms),
                    lease_renewal_ms=runtime.config.worker_lease_ms,
                )
        except LiveExecutionFailed as failure:
            reconcile_failure = (
                failure.reconcile if isinstance(failure, _SwarmStageFailed) else True
            )
            authority_after_failure = runtime.stores.owner_jobs.get_job(
                owner_user_id=lease.owner_user_id, job_id=lease.job_id
            )
            if authority_after_failure is not None and authority_after_failure.operation_state in {
                OperationState.COMPLETE,
                OperationState.FAILED,
                OperationState.BUDGET_HALTED,
                OperationState.TIMED_OUT,
                OperationState.FAILED_RECONCILE,
            }:
                _mark_failed_before_network(
                    runtime,
                    lease,
                    clock_ms=clock_ms,
                    reconcile=(
                        authority_after_failure.operation_state is OperationState.FAILED_RECONCILE
                    ),
                    reason="live_execution_failed",
                )
                retrieval.close()
                return _recover_terminal(
                    runtime,
                    operation_id=lease.operation_id,
                    owner_user_id=lease.owner_user_id,
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    now_ms=clock_ms(),
                    clock_ms=clock_ms,
                )
            target = (
                authority_after_failure.operation_state
                if authority_after_failure is not None
                and authority_after_failure.operation_state
                in {OperationState.FAILED, OperationState.FAILED_RECONCILE}
                else _mark_failed_before_network(
                    runtime,
                    lease,
                    clock_ms=clock_ms,
                    reconcile=reconcile_failure,
                    reason="live_execution_failed",
                )
            )
            target = _mark_failed_before_network(
                runtime,
                lease,
                clock_ms=clock_ms,
                reconcile=target is OperationState.FAILED_RECONCILE,
                reason="live_execution_failed",
            )
            try:
                failed_deposit = resume_terminal_deposit(
                    lease.job_id,
                    store=runtime.stores.jobs,
                    engagement_store=runtime.stores.engagement_store,
                    owner_user_id=lease.owner_user_id,
                )
            except Exception:
                return WorkerPhaseRecord(
                    result="deposit_pending",
                    phase="failed_iteration_deposit_pending",
                    worker_id=worker_id,
                    operation_id=lease.operation_id,
                    job_id=lease.job_id,
                    lease_generation=lease.lease_generation,
                    error_code="live_execution_failed",
                )
            _archive_current_lease(runtime, lease, terminal_state=target, clock_ms=clock_ms)
            return WorkerPhaseRecord(
                result=(
                    "reconcile_required" if target is OperationState.FAILED_RECONCILE else "failed"
                ),
                phase="paid_iteration_archived",
                worker_id=worker_id,
                operation_id=lease.operation_id,
                job_id=lease.job_id,
                lease_generation=lease.lease_generation,
                deposit_document_id=failed_deposit.document_id,
                error_code="live_execution_failed",
            )
        except Exception:
            authority_after_exception = runtime.stores.owner_jobs.get_job(
                owner_user_id=lease.owner_user_id, job_id=lease.job_id
            )
            if (
                authority_after_exception is not None
                and authority_after_exception.operation_state
                in {
                    OperationState.COMPLETE,
                    OperationState.FAILED,
                    OperationState.BUDGET_HALTED,
                    OperationState.TIMED_OUT,
                    OperationState.FAILED_RECONCILE,
                }
            ):
                _mark_failed_before_network(
                    runtime,
                    lease,
                    clock_ms=clock_ms,
                    reconcile=(
                        authority_after_exception.operation_state is OperationState.FAILED_RECONCILE
                    ),
                    reason="ambiguous_iteration",
                )
                retrieval.close()
                return _recover_terminal(
                    runtime,
                    operation_id=lease.operation_id,
                    owner_user_id=lease.owner_user_id,
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    now_ms=clock_ms(),
                    clock_ms=clock_ms,
                )
            target = _mark_failed_before_network(
                runtime,
                lease,
                clock_ms=clock_ms,
                reconcile=True,
                reason="ambiguous_iteration",
            )
            try:
                ambiguous_deposit = resume_terminal_deposit(
                    lease.job_id,
                    store=runtime.stores.jobs,
                    engagement_store=runtime.stores.engagement_store,
                    owner_user_id=lease.owner_user_id,
                )
            except Exception:
                return WorkerPhaseRecord(
                    result="deposit_pending",
                    phase="ambiguous_iteration_deposit_pending",
                    worker_id=worker_id,
                    operation_id=lease.operation_id,
                    job_id=lease.job_id,
                    lease_generation=lease.lease_generation,
                    error_code="ambiguous_iteration",
                )
            _archive_current_lease(runtime, lease, terminal_state=target, clock_ms=clock_ms)
            return WorkerPhaseRecord(
                result="reconcile_required",
                phase="ambiguous_iteration_archived",
                worker_id=worker_id,
                operation_id=lease.operation_id,
                job_id=lease.job_id,
                lease_generation=lease.lease_generation,
                deposit_document_id=ambiguous_deposit.document_id,
                error_code="ambiguous_iteration",
            )
    finally:
        retrieval.close()

    if is_swarm and swarm_run is not None and not swarm_run[1]:
        return WorkerPhaseRecord(
            result="lease_pending",
            phase=("shutdown_after_swarm_stage" if stop_requested() else "swarm_stage_settled"),
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
        )
    if stop_requested():
        return WorkerPhaseRecord(
            result="deposit_pending",
            phase="shutdown_after_provider",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
        )
    _renew(runtime, lease, clock_ms=clock_ms)
    try:
        deposit = resume_terminal_deposit(
            lease.job_id,
            store=runtime.stores.jobs,
            engagement_store=runtime.stores.engagement_store,
            owner_user_id=lease.owner_user_id,
        )
    except Exception:
        return WorkerPhaseRecord(
            result="deposit_pending",
            phase="deposit_failed",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            error_code="deposit_failed",
        )
    terminal_job = get_job(lease.job_id, store=runtime.stores.jobs)
    if terminal_job is None:
        raise RuntimeError("deposited operation lost job details")
    terminal_authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if terminal_authority is None:
        raise RuntimeError("deposited operation lost terminal authority")
    try:
        finalize_bound_session(
            authority=terminal_authority,
            job=terminal_job,
            engagement_store=runtime.stores.engagement_store,
            session_store=runtime.stores.session_store,
        )
    except Exception:
        return WorkerPhaseRecord(
            result="deposit_pending",
            phase="session_flywheel_pending",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            deposit_document_id=deposit.document_id,
            error_code="session_flywheel_pending",
        )
    if not terminal_job.step_evidence:
        _renew(runtime, lease, clock_ms=clock_ms)
        _archive_current_lease(
            runtime,
            lease,
            terminal_state=terminal_authority.operation_state,
            clock_ms=clock_ms,
        )
        result_by_state: dict[OperationState, WorkerResult] = {
            OperationState.BUDGET_HALTED: "budget_halted",
            OperationState.TIMED_OUT: "timed_out",
            OperationState.FAILED: "failed",
            OperationState.FAILED_RECONCILE: "reconcile_required",
        }
        return WorkerPhaseRecord(
            result=result_by_state.get(terminal_authority.operation_state, "failed"),
            phase="terminal_without_graph_archived",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            deposit_document_id=deposit.document_id,
        )
    if stop_requested():
        return WorkerPhaseRecord(
            result="projection_pending",
            phase="shutdown_after_deposit",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            deposit_document_id=deposit.document_id,
        )
    _renew(runtime, lease, clock_ms=clock_ms)
    try:
        graph = resume_terminal_projection(
            lease.job_id,
            owner_user_id=lease.owner_user_id,
            owner_jobs=runtime.stores.owner_jobs,
            store=runtime.stores.jobs,
            engagement_store=runtime.stores.engagement_store,
            graph_db_path=runtime.config.graph_db_path,
        )
    except Exception:
        return WorkerPhaseRecord(
            result="projection_pending",
            phase="projection_failed",
            worker_id=worker_id,
            operation_id=lease.operation_id,
            job_id=lease.job_id,
            lease_generation=lease.lease_generation,
            deposit_document_id=deposit.document_id,
            error_code="projection_failed",
        )
    _renew(runtime, lease, clock_ms=clock_ms)
    terminal_authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if terminal_authority is None:
        raise RuntimeError("completed operation lost owner authority")
    if not runtime.stores.operation_queue.acknowledge_terminal(
        operation_id=lease.operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        terminal_state=_terminal_state(terminal_authority.operation_state),
        completed_at_ms=clock_ms(),
    ):
        raise RuntimeError("completed operation lost its queue fence")
    return WorkerPhaseRecord(
        result="complete",
        phase="terminal_archived",
        worker_id=worker_id,
        operation_id=lease.operation_id,
        job_id=lease.job_id,
        lease_generation=lease.lease_generation,
        deposit_document_id=deposit.document_id,
        graph_deliverable_id=graph.receipt.deliverable_id,
        graph_html_sha256=graph.receipt.html_sha256,
    )


@dataclass(frozen=True)
class _SystemClock:
    read: Callable[[], int]

    def now_ms(self) -> int:
        return self.read()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antiek midnight-oil-worker")
    parser.add_argument("--config", required=True, help="Absolute runtime JSON path")
    parser.add_argument("--worker-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Process at most one operation")
    mode.add_argument("--poll", action="store_true", help="Poll until interrupted")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        runtime = build_worker_runtime(args.config)
        model = SentenceTransformerEmbedding(runtime.config.embedding_model_name)
    except (MidnightOilRuntimeConfigError, RuntimeError):
        sys.stderr.write('{"result":"failed","phase":"startup","error_code":"configuration"}\n')
        return 2
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while True:
        try:
            record = run_worker_once(
                runtime,
                worker_id=args.worker_id,
                embedding_model=model,
                stop_requested=stop.is_set,
            )
        except Exception as exc:  # sanitized process boundary
            record = WorkerPhaseRecord(
                result="failed",
                phase="worker_iteration",
                worker_id=args.worker_id,
                error_code=type(exc).__name__,
            )
        sys.stdout.write(record.to_json() + "\n")
        sys.stdout.flush()
        if stop.is_set():
            return 0
        if not args.poll:
            return 0 if record.result in {"no_work", "complete", "recovered"} else 1
        try:
            time.sleep(runtime.config.worker_poll_ms / 1000)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MidnightOilWorkerRuntime",
    "WorkerPhaseRecord",
    "build_worker_runtime",
    "main",
    "run_worker_once",
]
