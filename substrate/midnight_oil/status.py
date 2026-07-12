"""Owner-safe, read-only lifecycle projection for Midnight Oil operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from .budget_ledger import BudgetExposure
from .job import MidnightOilJob
from .job_store import OperationState, OwnerJob
from .operation_queue import OperationQueue, QueuedOperation, TerminalOperation

LifecycleState = Literal[
    "consent_required",
    "consent_issued",
    "consent_delivery_failed",
    "queued",
    "leased",
    "lease_pending",
    "blocked_provider",
    "reconcile_required",
    "deposit_pending",
    "projection_pending",
    "archive_pending",
    "complete",
    "failed",
    "budget_halted",
    "timed_out",
]
TerminalOutcome = Literal[
    "complete",
    "blocked_provider",
    "failed",
    "failed_reconcile",
    "budget_halted",
    "timed_out",
]
OperatorAction = Literal[
    "issue_consent",
    "reset_consent",
    "wait_for_worker",
    "restart_worker",
    "inspect_reconciliation",
    "open_html_result",
    "review_terminal_result",
]
CostState = Literal["not_reserved", "reserved", "unknown_outcome", "settled"]


class LifecycleIntegrityError(ValueError):
    """Durable stores disagree, so no optimistic status may be returned."""


@dataclass(frozen=True)
class MidnightOilLifecycleStatus:
    schema_version: int
    job_id: str
    operation_id: str | None
    state: LifecycleState
    terminal_outcome: TerminalOutcome | None
    approved_ceiling_cents: int | None
    confirmed_spent_cents: int
    reserved_cents: int
    unknown_outcome: bool
    remaining_cents: int | None
    cost_state: CostState
    consent_expires_at_ms: int | None
    enqueued_at_ms: int | None
    lease_expires_at_ms: int | None
    completed_at_ms: int | None
    deposit_document_id: str | None
    deposit_href: str | None
    graph_deliverable_id: str | None
    graph_deep_links: tuple[str, ...]
    operator_action: OperatorAction
    view_format: Literal["html"] = "html"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _spent_cents(job: MidnightOilJob) -> int:
    try:
        cents = Decimal(str(job.spent_usd)) * 100
    except InvalidOperation as exc:
        raise LifecycleIntegrityError("stored spend is invalid") from exc
    integral = cents.to_integral_value()
    if cents != integral or not 0 <= integral <= 1_000_000_000:
        raise LifecycleIntegrityError("stored spend is outside cent bounds")
    return int(integral)


def _matches(
    row: QueuedOperation | TerminalOperation,
    *,
    authority: OwnerJob,
) -> bool:
    return (
        row.operation_id == authority.operation_id
        and row.owner_user_id == authority.owner_user_id
        and row.job_id == authority.job_id
    )


def _terminal_outcome(authority: OwnerJob, job: MidnightOilJob) -> TerminalOutcome:
    if authority.operation_state is OperationState.COMPLETE:
        return "complete"
    if authority.operation_state is OperationState.FAILED_RECONCILE:
        return "failed_reconcile"
    if authority.operation_state is OperationState.BUDGET_HALTED:
        return "budget_halted"
    if authority.operation_state is OperationState.TIMED_OUT:
        return "timed_out"
    if authority.operation_state is OperationState.FAILED:
        return (
            "blocked_provider"
            if job.terminal_reason == "configuration_blocked"
            else "failed"
        )
    raise LifecycleIntegrityError("operation authority is not terminal")


def _validate_terminal_detail(authority: OwnerJob, job: MidnightOilJob) -> None:
    expected: dict[OperationState, str] = {
        OperationState.COMPLETE: "complete",
        OperationState.FAILED: "failed",
        OperationState.FAILED_RECONCILE: "failed",
        OperationState.BUDGET_HALTED: "budget_halted",
        OperationState.TIMED_OUT: "timed_out",
    }
    if job.status != expected.get(authority.operation_state):
        raise LifecycleIntegrityError("terminal detail conflicts with owner authority")
    if (
        job.terminal_reason == "configuration_blocked"
        and authority.operation_state is not OperationState.FAILED
    ):
        raise LifecycleIntegrityError("terminal reason conflicts with owner authority")
    if authority.operation_state is OperationState.COMPLETE and job.terminal_reason is not None:
        raise LifecycleIntegrityError("completed job carries a failure reason")


def _terminal_state(
    *, authority: OwnerJob, job: MidnightOilJob
) -> tuple[LifecycleState, TerminalOutcome, OperatorAction]:
    outcome = _terminal_outcome(authority, job)
    if (
        job.deposit_state != "complete"
        or not job.deposit_document_id
        or not job.deposit_html_sha256
    ):
        return "deposit_pending", outcome, "restart_worker"
    if outcome == "complete":
        if not job.step_evidence:
            return "reconcile_required", outcome, "inspect_reconciliation"
        if job.graph_projection_state != "complete" or job.graph_effect_receipt is None:
            return "projection_pending", outcome, "restart_worker"
        return "complete", outcome, "open_html_result"
    if outcome == "failed_reconcile":
        return "reconcile_required", outcome, "inspect_reconciliation"
    if outcome == "blocked_provider":
        return "blocked_provider", outcome, "review_terminal_result"
    return outcome, outcome, "review_terminal_result"


def project_lifecycle_status(
    *,
    authority: OwnerJob,
    job: MidnightOilJob,
    operation_queue: OperationQueue,
    now_ms: int,
    budget_exposure: BudgetExposure | None = None,
) -> MidnightOilLifecycleStatus:
    """Join durable stores without mutation or body/error disclosure."""

    if type(now_ms) is not int or now_ms < 0:
        raise ValueError("now_ms must be non-negative")
    if authority.job_id != job.job_id:
        raise LifecycleIntegrityError("owner authority and detail job disagree")
    detail_spent = _spent_cents(job)
    confirmed_spent = 0
    reserved_cents = 0
    unknown_outcome = False
    remaining_cents: int | None = authority.approved_ceiling_cents
    cost_state: CostState = "not_reserved"
    if budget_exposure is not None:
        if budget_exposure.run_id != job.job_id:
            raise LifecycleIntegrityError("budget exposure belongs to another job")
        if budget_exposure.ceiling_cents != authority.approved_ceiling_cents:
            raise LifecycleIntegrityError("budget ceiling conflicts with owner authority")
        confirmed_spent = budget_exposure.confirmed_spent_cents
        reserved_cents = (
            budget_exposure.open_held_cents + budget_exposure.unknown_held_cents
        )
        unknown_outcome = budget_exposure.unknown_held_cents > 0
        remaining_cents = budget_exposure.remaining_cents
        cost_state = (
            "unknown_outcome"
            if unknown_outcome
            else ("reserved" if reserved_cents else "settled")
        )
        if detail_spent > confirmed_spent:
            raise LifecycleIntegrityError("job spend exceeds the authoritative ledger")
    elif detail_spent != 0:
        raise LifecycleIntegrityError("job spend exists without an authoritative ledger")
    if (
        authority.approved_ceiling_cents is not None
        and confirmed_spent + reserved_cents > authority.approved_ceiling_cents
    ):
        raise LifecycleIntegrityError("budget exposure exceeds owner-approved authority")
    if (
        job.graph_effect_receipt is not None
        and job.graph_effect_receipt.owner_user_id != authority.owner_user_id
    ):
        raise LifecycleIntegrityError("graph receipt conflicts with owner authority")
    operation_id = authority.operation_id
    active: QueuedOperation | None = None
    archived: TerminalOperation | None = None
    if operation_id is not None:
        active = operation_queue.get(operation_id)
        archived = operation_queue.get_terminal(operation_id)
        if active is not None and not _matches(active, authority=authority):
            raise LifecycleIntegrityError("active queue row conflicts with owner authority")
        if archived is not None and not _matches(archived, authority=authority):
            raise LifecycleIntegrityError("terminal queue row conflicts with owner authority")
        if active is not None and archived is not None:
            raise LifecycleIntegrityError("operation is both active and terminal")

    state: LifecycleState
    outcome: TerminalOutcome | None = None
    action: OperatorAction
    if authority.operation_state is OperationState.NONE:
        if operation_id is not None or active is not None or archived is not None:
            raise LifecycleIntegrityError("unconsented job has operation authority")
        state, action = "consent_required", "issue_consent"
    elif authority.operation_state is OperationState.CONSENT_ISSUED:
        if operation_id is None or active is not None or archived is not None:
            raise LifecycleIntegrityError("consent-issued job has incoherent delivery state")
        state, action = "consent_issued", "reset_consent"
    elif authority.operation_state is OperationState.QUEUED:
        if active is None and archived is None:
            state, action = "consent_delivery_failed", "reset_consent"
        elif active is None or active.state != "queued" or archived is not None:
            state, action = "reconcile_required", "inspect_reconciliation"
        else:
            state, action = "queued", "wait_for_worker"
    elif authority.operation_state is OperationState.RUNNING:
        if active is None or active.state != "running" or archived is not None:
            state, action = "reconcile_required", "inspect_reconciliation"
        elif active.lease_expires_at_ms is None or active.lease_expires_at_ms <= now_ms:
            state, action = "lease_pending", "restart_worker"
        else:
            state, action = "leased", "wait_for_worker"
    else:
        _validate_terminal_detail(authority, job)
        expected_archive = authority.operation_state.value
        if archived is not None and archived.terminal_state != expected_archive:
            raise LifecycleIntegrityError("terminal archive conflicts with owner authority")
        if active is not None and active.state != "running":
            raise LifecycleIntegrityError("terminal recovery queue row is not leased")
        if active is None and archived is None:
            state, outcome, action = (
                "reconcile_required",
                _terminal_outcome(authority, job),
                "inspect_reconciliation",
            )
        else:
            state, outcome, action = _terminal_state(authority=authority, job=job)
            if state == "complete" and archived is None:
                state = "archive_pending"
                action = (
                    "restart_worker"
                    if active is not None
                    and active.lease_expires_at_ms is not None
                    and active.lease_expires_at_ms <= now_ms
                    else "wait_for_worker"
                )

    if authority.operation_state is OperationState.FAILED_RECONCILE:
        unknown_outcome = reserved_cents > 0
        if budget_exposure is None or not unknown_outcome:
            raise LifecycleIntegrityError(
                "reconciliation authority lacks unsettled budget exposure"
            )
        cost_state = "unknown_outcome"
    if authority.operation_state is OperationState.COMPLETE and (
        budget_exposure is None or reserved_cents or detail_spent != confirmed_spent
    ):
        raise LifecycleIntegrityError("completed operation budget is not settled")

    receipt = job.graph_effect_receipt
    deposit_id = (
        job.deposit_document_id
        if job.deposit_state == "complete" and job.deposit_html_sha256
        else None
    )
    return MidnightOilLifecycleStatus(
        schema_version=1,
        job_id=authority.job_id,
        operation_id=operation_id,
        state=state,
        terminal_outcome=outcome,
        approved_ceiling_cents=authority.approved_ceiling_cents,
        confirmed_spent_cents=confirmed_spent,
        reserved_cents=reserved_cents,
        unknown_outcome=unknown_outcome,
        remaining_cents=remaining_cents,
        cost_state=cost_state,
        consent_expires_at_ms=authority.consent_expires_at_ms,
        enqueued_at_ms=(None if active is None else active.enqueued_at_ms),
        lease_expires_at_ms=(None if active is None else active.lease_expires_at_ms),
        completed_at_ms=(
            authority.completed_at_ms
            if authority.completed_at_ms is not None
            else (None if archived is None else archived.completed_at_ms)
        ),
        deposit_document_id=deposit_id,
        deposit_href=(
            None
            if deposit_id is None
            else f"/midnight-oil/jobs/{authority.job_id}/artifact"
        ),
        graph_deliverable_id=(None if receipt is None else receipt.deliverable_id),
        graph_deep_links=() if receipt is None else receipt.deep_links,
        operator_action=action,
    )


__all__ = [
    "LifecycleIntegrityError",
    "MidnightOilLifecycleStatus",
    "project_lifecycle_status",
]
