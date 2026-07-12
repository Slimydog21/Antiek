"""Durable Midnight Oil worker process and ``antiek midnight-oil-worker`` CLI."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, Protocol, cast

from substrate.dispatch import DispatchConfig
from substrate.graph.retrieval_substrate import RetrievalSubstrate, make_substrate
from substrate.graph.search import EmbeddingModel, SentenceTransformerEmbedding

from .job import get_job, put_job_state
from .job_store import InvalidStoredJob, OperationState
from .live import (
    LiveExecutionFailed,
    RouterIdempotentDispatch,
    live_plan_from_authority,
    resume_terminal_deposit,
    resume_terminal_projection,
    run_authorized_live_iteration,
)
from .runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeConfigError,
    MidnightOilRuntimeStores,
    build_runtime_stores,
    install_attested_providers,
)
from .worker import (
    LeaseContentionError,
    LeaseValidationError,
    OperationNotDispatchableError,
    WorkerLease,
    lease_authorized_operation,
)

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


def build_worker_runtime(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> MidnightOilWorkerRuntime:
    environment = os.environ if environ is None else environ
    config = MidnightOilRuntimeConfig.from_file(config_path)
    install_attested_providers(config, environment)
    return MidnightOilWorkerRuntime(
        config=config,
        stores=build_runtime_stores(config),
        dispatch_config=DispatchConfig.from_yaml(config.dispatch_config_path),
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
    if job is not None and job.status not in {
        "complete",
        "timed_out",
        "budget_halted",
        "failed",
    }:
        put_job_state(replace(job, status="failed"), store=runtime.stores.jobs)
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
        return WorkerPhaseRecord(
            result="contended",
            phase="terminal_queue_resolved",
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
    try:
        authority = runtime.stores.owner_jobs.get_job(
            owner_user_id=owner_user_id, job_id=job_id
        )
    except (InvalidStoredJob, TypeError, ValueError):
        if not queue.acknowledge_terminal(
            operation_id=operation_id,
            worker_id=worker_id,
            lease_generation=leased.lease_generation,
            terminal_state="failed_reconcile",
            completed_at_ms=now_ms,
        ):
            raise RuntimeError(
                "malformed authority quarantine lost its queue fence"
            ) from None
        return WorkerPhaseRecord(
            result="reconcile_required",
            phase="lease_validation_authority_malformed",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
            lease_generation=leased.lease_generation,
            error_code="authority_malformed",
        )
    if authority is None or authority.operation_id != operation_id:
        raise ValueError("terminal recovery lacks matching owner authority")
    deposit = resume_terminal_deposit(
        job_id,
        store=runtime.stores.jobs,
        engagement_store=runtime.stores.engagement_store,
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


def _quarantine_lease_validation(
    runtime: MidnightOilWorkerRuntime,
    *,
    operation_id: str,
    owner_user_id: str,
    job_id: str,
    worker_id: str,
    now_ms: int,
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
        return WorkerPhaseRecord(
            result="contended",
            phase="lease_validation_queue_resolved",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
        )
    if not won:
        return WorkerPhaseRecord(
            result="contended",
            phase="lease_validation_quarantine_contended",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
        )
    try:
        authority = runtime.stores.owner_jobs.get_job(
            owner_user_id=owner_user_id, job_id=job_id
        )
    except (InvalidStoredJob, TypeError, ValueError):
        if not queue.acknowledge_terminal(
            operation_id=operation_id,
            worker_id=worker_id,
            lease_generation=leased.lease_generation,
            terminal_state="failed_reconcile",
            completed_at_ms=now_ms,
        ):
            raise RuntimeError(
                "malformed authority quarantine lost its queue fence"
            ) from None
        return WorkerPhaseRecord(
            result="reconcile_required",
            phase="lease_validation_authority_malformed",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
            lease_generation=leased.lease_generation,
            error_code="authority_malformed",
        )
    quarantined_here = False
    quarantined_from: OperationState | None = None
    if (
        authority is not None
        and authority.operation_id == operation_id
        and authority.operation_state
        in {
            OperationState.CONSENT_ISSUED,
            OperationState.QUEUED,
            OperationState.RUNNING,
        }
    ):
        quarantined_from = authority.operation_state
        changed = runtime.stores.owner_jobs.compare_and_set(
            owner_user_id=owner_user_id,
            job_id=job_id,
            expected_version=authority.state_version,
            expected_state=authority.operation_state,
            operation_id=operation_id,
            next_state=OperationState.FAILED_RECONCILE,
            completed_at_ms=now_ms,
        )
        quarantined_here = changed.applied
        authority = changed.job
    if (
        authority is None
        or authority.operation_id != operation_id
        or authority.operation_state
        not in {
            OperationState.COMPLETE,
            OperationState.FAILED,
            OperationState.BUDGET_HALTED,
            OperationState.TIMED_OUT,
            OperationState.FAILED_RECONCILE,
        }
    ):
        return WorkerPhaseRecord(
            result="contended",
            phase="lease_validation_authority_contended",
            worker_id=worker_id,
            operation_id=operation_id,
            job_id=job_id,
            lease_generation=leased.lease_generation,
        )
    if not quarantined_here:
        return _recover_terminal(
            runtime,
            operation_id=operation_id,
            owner_user_id=owner_user_id,
            job_id=job_id,
            worker_id=worker_id,
            now_ms=now_ms,
            clock_ms=lambda: now_ms,
        )
    if quarantined_from is OperationState.RUNNING:
        return _recover_terminal(
            runtime,
            operation_id=operation_id,
            owner_user_id=owner_user_id,
            job_id=job_id,
            worker_id=worker_id,
            now_ms=now_ms,
            clock_ms=lambda: now_ms,
        )
    if not queue.acknowledge_terminal(
        operation_id=operation_id,
        worker_id=worker_id,
        lease_generation=leased.lease_generation,
        terminal_state=_terminal_state(authority.operation_state),
        completed_at_ms=now_ms,
    ):
        raise RuntimeError("lease validation quarantine lost its queue fence")
    return WorkerPhaseRecord(
        result="reconcile_required",
        phase="lease_validation_quarantined",
        worker_id=worker_id,
        operation_id=operation_id,
        job_id=job_id,
        lease_generation=leased.lease_generation,
        error_code="lease_validation",
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
        return WorkerPhaseRecord(
            result="no_work", phase="queue_empty", worker_id=worker_id
        )
    try:
        authority = runtime.stores.owner_jobs.get_job(
            owner_user_id=queued.owner_user_id, job_id=queued.job_id
        )
    except (InvalidStoredJob, TypeError, ValueError):
        authority = None
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
        )
    except LeaseContentionError:
        return WorkerPhaseRecord(
            result="contended",
            phase="lease_not_acquired",
            worker_id=worker_id,
            operation_id=queued.operation_id,
            job_id=queued.job_id,
        )
    except OperationNotDispatchableError:
        try:
            refreshed = runtime.stores.owner_jobs.get_job(
                owner_user_id=queued.owner_user_id, job_id=queued.job_id
            )
        except (InvalidStoredJob, TypeError, ValueError):
            return _quarantine_lease_validation(
                runtime,
                operation_id=queued.operation_id,
                owner_user_id=queued.owner_user_id,
                job_id=queued.job_id,
                worker_id=worker_id,
                now_ms=now_ms,
            )
        if refreshed is not None and refreshed.operation_state in {
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
        return _quarantine_lease_validation(
            runtime,
            operation_id=queued.operation_id,
            owner_user_id=queued.owner_user_id,
            job_id=queued.job_id,
            worker_id=worker_id,
            now_ms=now_ms,
        )
    except LeaseValidationError:
        return _quarantine_lease_validation(
            runtime,
            operation_id=queued.operation_id,
            owner_user_id=queued.owner_user_id,
            job_id=queued.job_id,
            worker_id=worker_id,
            now_ms=now_ms,
        )
    running_authority = runtime.stores.owner_jobs.get_job(
        owner_user_id=lease.owner_user_id, job_id=lease.job_id
    )
    if running_authority is None:
        raise RuntimeError("leased operation lost owner authority")
    try:
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
            runtime, lease, clock_ms=clock_ms, reconcile=False
        )
        try:
            deposit = resume_terminal_deposit(
                lease.job_id,
                store=runtime.stores.jobs,
                engagement_store=runtime.stores.engagement_store,
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
        _archive_current_lease(
            runtime, lease, terminal_state=target, clock_ms=clock_ms
        )
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

    try:
        try:
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
        except LiveExecutionFailed:
            authority_after_failure = runtime.stores.owner_jobs.get_job(
                owner_user_id=lease.owner_user_id, job_id=lease.job_id
            )
            if (
                authority_after_failure is not None
                and authority_after_failure.operation_state
                in {
                    OperationState.COMPLETE,
                    OperationState.FAILED,
                    OperationState.BUDGET_HALTED,
                    OperationState.TIMED_OUT,
                    OperationState.FAILED_RECONCILE,
                }
            ):
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
                    runtime, lease, clock_ms=clock_ms, reconcile=True
                )
            )
            target = _mark_failed_before_network(
                runtime,
                lease,
                clock_ms=clock_ms,
                reconcile=target is OperationState.FAILED_RECONCILE,
            )
            try:
                failed_deposit = resume_terminal_deposit(
                    lease.job_id,
                    store=runtime.stores.jobs,
                    engagement_store=runtime.stores.engagement_store,
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
            _archive_current_lease(
                runtime, lease, terminal_state=target, clock_ms=clock_ms
            )
            return WorkerPhaseRecord(
                result=(
                    "reconcile_required"
                    if target is OperationState.FAILED_RECONCILE
                    else "failed"
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
                runtime, lease, clock_ms=clock_ms, reconcile=True
            )
            try:
                ambiguous_deposit = resume_terminal_deposit(
                    lease.job_id,
                    store=runtime.stores.jobs,
                    engagement_store=runtime.stores.engagement_store,
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
            _archive_current_lease(
                runtime, lease, terminal_state=target, clock_ms=clock_ms
            )
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
    if not terminal_job.step_evidence:
        terminal_authority = runtime.stores.owner_jobs.get_job(
            owner_user_id=lease.owner_user_id, job_id=lease.job_id
        )
        if terminal_authority is None:
            raise RuntimeError("deposited operation lost terminal authority")
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
