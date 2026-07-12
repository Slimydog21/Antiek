from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import BudgetExposure
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    JobStatus,
    MidnightOilGraphEffectReceipt,
    MidnightOilStepEvidence,
    create_job,
)
from substrate.midnight_oil.job_store import OperationState, OwnerJob
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.status import LifecycleIntegrityError, project_lifecycle_status


def _job():  # type: ignore[no-untyped-def]
    return create_job(
        ["Trace a durable lifecycle."],
        10,
        store=InMemoryJobStore(),
        job_id="status-job",
        asset_id="status-asset",
    )


def _owner(state: OperationState, operation_id: str | None) -> OwnerJob:
    return OwnerJob(
        owner_user_id="status-owner",
        job_id="status-job",
        state_version=1,
        approved_ceiling_cents=None if state is OperationState.NONE else 500,
        consent_receipt_id=None if state is OperationState.NONE else "receipt",
        consent_config_hash=None if state is OperationState.NONE else "c" * 64,
        consent_issued_at_ms=None if state is OperationState.NONE else 10,
        consent_expires_at_ms=None if state is OperationState.NONE else 1000,
        consent_claimed_at_ms=(
            20
            if state
            not in {OperationState.NONE, OperationState.CONSENT_ISSUED}
            else None
        ),
        operation_id=operation_id,
        operation_state=state,
        dispatch_started_at_ms=30 if state is OperationState.RUNNING else None,
        dispatched_at_ms=None,
        completed_at_ms=(
            60
            if state
            in {
                OperationState.COMPLETE,
                OperationState.FAILED,
                OperationState.BUDGET_HALTED,
                OperationState.TIMED_OUT,
                OperationState.FAILED_RECONCILE,
            }
            else None
        ),
        payload={},
    )


def _enqueue(queue: DurableOperationQueue):  # type: ignore[no-untyped-def]
    return queue.enqueue_once(
        operation_id="status-operation",
        owner_user_id="status-owner",
        job_id="status-job",
        enqueued_at_ms=20,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )[0]


def _settled_exposure() -> BudgetExposure:
    return BudgetExposure(
        run_id="status-job",
        ceiling_cents=500,
        confirmed_spent_cents=0,
        open_held_cents=0,
        unknown_held_cents=0,
        remaining_cents=500,
        status="reserved",
    )


def test_status_projects_consent_queue_and_lease_without_mutation(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    job = _job()

    initial = project_lifecycle_status(
        authority=_owner(OperationState.NONE, None),
        job=job,
        operation_queue=queue,
        now_ms=1,
    )
    assert (initial.state, initial.operator_action) == (
        "consent_required",
        "issue_consent",
    )

    consent = project_lifecycle_status(
        authority=_owner(OperationState.CONSENT_ISSUED, "status-operation"),
        job=job,
        operation_queue=queue,
        now_ms=11,
    )
    assert consent.state == "consent_issued"

    delivery_failed = project_lifecycle_status(
        authority=_owner(OperationState.QUEUED, "status-operation"),
        job=job,
        operation_queue=queue,
        now_ms=19,
    )
    assert (delivery_failed.state, delivery_failed.operator_action) == (
        "consent_delivery_failed",
        "reset_consent",
    )

    queued = _enqueue(queue)
    queued_status = project_lifecycle_status(
        authority=_owner(OperationState.QUEUED, queued.operation_id),
        job=job,
        operation_queue=queue,
        now_ms=21,
    )
    assert queued_status.state == "queued"

    leased, won = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert won
    authority = _owner(OperationState.RUNNING, leased.operation_id)
    assert project_lifecycle_status(
        authority=authority, job=job, operation_queue=queue, now_ms=49
    ).state == "leased"
    assert project_lifecycle_status(
        authority=authority, job=job, operation_queue=queue, now_ms=50
    ).state == "lease_pending"
    assert queue.get(queued.operation_id) == leased


def test_status_projects_terminal_persistence_phases_and_links(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    queued = _enqueue(queue)
    leased, _ = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="status-worker",
        lease_generation=leased.lease_generation,
        terminal_state="complete",
        completed_at_ms=60,
    )
    authority = _owner(OperationState.COMPLETE, leased.operation_id)
    evidence = MidnightOilStepEvidence(
        step_key="step-1",
        spawn_id="spawn-1",
        output_text="Result",
        insights=("Insight",),
        questions=("Question?",),
    )
    pending = replace(_job(), status="complete", step_evidence=(evidence,))
    assert project_lifecycle_status(
        authority=authority,
        job=pending,
        operation_queue=queue,
        now_ms=61,
        budget_exposure=_settled_exposure(),
    ).state == "deposit_pending"

    deposited = replace(
        pending,
        deposit_state="complete",
        deposit_document_id="status-document",
        deposit_html_sha256="c" * 64,
    )
    projected_pending = project_lifecycle_status(
        authority=authority, job=deposited, operation_queue=queue, now_ms=61
        , budget_exposure=_settled_exposure()
    )
    assert projected_pending.state == "projection_pending"
    assert projected_pending.deposit_href == "/midnight-oil/jobs/status-job/artifact"

    receipt = MidnightOilGraphEffectReceipt(
        schema_version=1,
        owner_user_id="status-owner",
        deliverable_id="dlv-0123456789abcdef",
        section_ids=("sec-0123456789abcdef",),
        node_ids=("node-0123456789abcdef",),
        edge_ids=("edge-0123456789abcdef",),
        html_sha256="a" * 64,
        evidence_sha256="b" * 64,
        deep_links=(
            "antiek://deliverable/dlv-0123456789abcdef",
            "antiek://node/node-0123456789abcdef",
        ),
    )
    complete = project_lifecycle_status(
        authority=authority,
        job=replace(
            deposited,
            graph_projection_state="complete",
            graph_effect_receipt=receipt,
        ),
        operation_queue=queue,
        now_ms=61,
        budget_exposure=_settled_exposure(),
    )
    assert complete.state == "complete"
    assert complete.graph_deliverable_id == receipt.deliverable_id
    assert complete.graph_deep_links == receipt.deep_links


def test_status_preserves_blocked_provider_reason_after_archive(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    queued = _enqueue(queue)
    leased, _ = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="status-worker",
        lease_generation=leased.lease_generation,
        terminal_state="failed",
        completed_at_ms=60,
    )
    status = project_lifecycle_status(
        authority=_owner(OperationState.FAILED, leased.operation_id),
        job=replace(
            _job(),
            status="failed",
            terminal_reason="configuration_blocked",
            deposit_state="complete",
            deposit_document_id="status-document",
            deposit_html_sha256="c" * 64,
        ),
        operation_queue=queue,
        now_ms=61,
    )
    assert status.state == "blocked_provider"
    assert status.terminal_outcome == "blocked_provider"


def test_status_fails_closed_on_terminal_archive_conflict(tmp_path: Path) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    queued = _enqueue(queue)
    leased, _ = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="status-worker",
        lease_generation=leased.lease_generation,
        terminal_state="complete",
        completed_at_ms=60,
    )
    with pytest.raises(LifecycleIntegrityError, match="archive conflicts"):
        project_lifecycle_status(
            authority=_owner(OperationState.FAILED, leased.operation_id),
            job=replace(_job(), status="failed"),
            operation_queue=queue,
            now_ms=61,
        )


@pytest.mark.parametrize(
    ("authority_state", "archive_state", "detail_status"),
    [
        (OperationState.COMPLETE, "complete", "failed"),
        (OperationState.FAILED, "failed", "complete"),
        (OperationState.FAILED_RECONCILE, "failed_reconcile", "complete"),
        (OperationState.BUDGET_HALTED, "budget_halted", "timed_out"),
        (OperationState.TIMED_OUT, "timed_out", "budget_halted"),
    ],
)
def test_status_fails_closed_on_terminal_detail_conflict(
    tmp_path: Path,
    authority_state: OperationState,
    archive_state: str,
    detail_status: JobStatus,
) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    queued = _enqueue(queue)
    leased, _ = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="status-worker",
        lease_generation=leased.lease_generation,
        terminal_state=archive_state,
        completed_at_ms=60,
    )
    with pytest.raises(LifecycleIntegrityError, match="detail conflicts"):
        project_lifecycle_status(
            authority=_owner(authority_state, leased.operation_id),
            job=replace(_job(), status=detail_status),
            operation_queue=queue,
            now_ms=61,
            budget_exposure=_settled_exposure(),
        )


def test_status_exposes_unknown_budget_without_claiming_zero_spend(
    tmp_path: Path,
) -> None:
    queue = DurableOperationQueue(tmp_path / "status.sqlite3")
    queued = _enqueue(queue)
    leased, _ = queue.lease(
        operation_id=queued.operation_id,
        worker_id="status-worker",
        leased_at_ms=30,
        lease_expires_at_ms=50,
    )
    assert queue.acknowledge_terminal(
        operation_id=leased.operation_id,
        worker_id="status-worker",
        lease_generation=leased.lease_generation,
        terminal_state="failed_reconcile",
        completed_at_ms=60,
    )
    exposure = BudgetExposure(
        run_id="status-job",
        ceiling_cents=500,
        confirmed_spent_cents=0,
        open_held_cents=0,
        unknown_held_cents=125,
        remaining_cents=375,
        status="reserved",
    )
    status = project_lifecycle_status(
        authority=_owner(OperationState.FAILED_RECONCILE, leased.operation_id),
        job=replace(
            _job(),
            status="failed",
            terminal_reason="ambiguous_iteration",
            deposit_state="complete",
            deposit_document_id="status-document",
            deposit_html_sha256="c" * 64,
        ),
        operation_queue=queue,
        now_ms=61,
        budget_exposure=exposure,
    )
    assert status.state == "reconcile_required"
    assert status.confirmed_spent_cents == 0
    assert status.reserved_cents == 125
    assert status.unknown_outcome is True
    assert status.cost_state == "unknown_outcome"
