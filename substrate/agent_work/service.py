"""Transactional, idempotent commands for bridge-delivered agent work."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from runtime.db_lock import connect_write
from substrate.agent_work.domain import MarkAcknowledged, MarkWorking, ResultKind
from substrate.agent_work.store import (
    AgentWorkStore,
    LeaseRenewal,
    ReplyCompletion,
    WorkLease,
    WorkProgress,
)
from substrate.feedback.schema import init_feedback_schema
from substrate.schemas.events import (
    AgentWorkTransitionedPayload,
    ArtifactFeedbackRepliedPayload,
)
from substrate.write.event_outbox import (
    build_typed_envelope,
    enqueue_event,
    eventful_transaction,
)


@dataclass(frozen=True, slots=True)
class CompleteReplyCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    context_sha256: str
    reply_item_id: str
    reply_markdown: str
    agent_id: str
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class CompleteFailureCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    context_sha256: str
    error_code: str
    retryable: bool
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class CompleteDispositionCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    context_sha256: str
    kind: Literal["decline", "approval_request"]
    message_item_id: str
    message_markdown: str
    agent_id: str
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class LeaseWorkCommand:
    logical_worker_id: str
    bridge_credential_id: str
    bridge_instance_id: str
    lease_id: str
    lease_seconds: int
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class MarkSubmittedCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    adapter_version: str
    herdr_target_observed: str
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class RenewLeaseCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    lease_seconds: int
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class MarkAcknowledgedCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    transport_receipt_sha256: str
    idempotency_key: str
    now: datetime


@dataclass(frozen=True, slots=True)
class MarkWorkingCommand:
    work_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    bridge_credential_id: str
    idempotency_key: str
    now: datetime


def _lease_request_sha256(command: LeaseWorkCommand) -> str:
    canonical = json.dumps(
        {
            "bridge_instance_id": command.bridge_instance_id,
            "lease_id": command.lease_id,
            "lease_seconds": command.lease_seconds,
            "logical_worker_id": command.logical_worker_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def lease_agent_work(
    db_path: str,
    command: LeaseWorkCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkLease | None:
    """Atomically lease, audit, and exactly replay one polling command."""
    request_sha256 = _lease_request_sha256(command)
    with connect_write(db_path, purpose="agent_work/lease") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='lease' AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            store = AgentWorkStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                if str(receipt[1]) == "none":
                    return None
                replay = store.get_lease(
                    con,
                    logical_worker_id=command.logical_worker_id,
                    bridge_credential_id=command.bridge_credential_id,
                    lease_id=str(receipt[1]),
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("lease receipt has no canonical result")
                return replay

            recovered = store.reclaim_expired(
                con,
                logical_worker_id=command.logical_worker_id,
                now=command.now,
            )
            for expired in recovered:
                investigation_id = str(
                    con.execute(
                        "SELECT investigation_id FROM feedback_threads WHERE thread_id=?",
                        [expired.thread_id],
                    ).fetchone()[0]
                )
                reason = (
                    "lease_expired"
                    if expired.state == "queued"
                    else "attempts_exhausted"
                )
                transitioned = build_typed_envelope(
                    investigation_id,
                    AgentWorkTransitionedPayload(
                        work_id=expired.work_id,
                        thread_id=expired.thread_id,
                        before_state=expired.before_state,
                        after_state=expired.state,
                        attempt_no=expired.attempt_no,
                        reason=reason,
                    ),
                    event_id=(
                        f"evt-agent-work-{reason}-{expired.work_id}-{expired.attempt_no}"
                    ),
                    emitted_at=command.now,
                )
                enqueue_event(
                    con,
                    operation_id=(
                        f"agent-transition:{expired.work_id}:{expired.attempt_no}:{reason}"
                    ),
                    aggregate_kind="agent_work",
                    aggregate_id=expired.work_id,
                    event=transitioned,
                )
            lease = store.lease_one(
                con,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                bridge_instance_id=command.bridge_instance_id,
                lease_id=command.lease_id,
                now=command.now,
                lease_seconds=command.lease_seconds,
            )
            if checkpoint is not None:
                checkpoint("after_lease_store")
            resource_id = "none" if lease is None else lease.lease_id
            if lease is not None:
                investigation_id = str(
                    con.execute(
                        "SELECT investigation_id FROM feedback_threads WHERE thread_id=?",
                        [lease.thread_id],
                    ).fetchone()[0]
                )
                transitioned = build_typed_envelope(
                    investigation_id,
                    AgentWorkTransitionedPayload(
                        work_id=lease.work_id,
                        thread_id=lease.thread_id,
                        before_state="queued",
                        after_state="leased",
                        attempt_no=lease.attempt_no,
                        reason="bridge_lease",
                    ),
                    event_id=f"evt-agent-work-leased-{lease.work_id}-{lease.attempt_no}",
                    emitted_at=command.now,
                )
                enqueue_event(
                    con,
                    operation_id=(
                        f"agent-transition:{lease.work_id}:{lease.attempt_no}:leased"
                    ),
                    aggregate_kind="agent_work",
                    aggregate_id=lease.work_id,
                    event=transitioned,
                )
                if checkpoint is not None:
                    checkpoint("after_lease_event")
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, resource_id"
                ") VALUES (?, 'lease', ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    resource_id,
                ],
            )
            if checkpoint is not None:
                checkpoint("after_lease_receipt")
            return lease


def renew_agent_work_lease(
    db_path: str,
    command: RenewLeaseCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> LeaseRenewal:
    """Atomically renew a live lease and exactly replay its first response."""
    request_sha256 = hashlib.sha256(
        json.dumps(
            {
                "attempt_no": command.attempt_no,
                "lease_id": command.lease_id,
                "lease_seconds": command.lease_seconds,
                "logical_worker_id": command.logical_worker_id,
                "work_id": command.work_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with connect_write(db_path, purpose="agent_work/renew") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, response_json FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='renew' AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                if receipt[1] is None:  # pragma: no cover - database invariant
                    raise RuntimeError("renew receipt has no canonical response")
                body = json.loads(str(receipt[1]))
                return LeaseRenewal(
                    work_id=str(body["work_id"]),
                    thread_id=str(body["thread_id"]),
                    state=str(body["state"]),
                    attempt_no=int(body["attempt_no"]),
                    lease_id=str(body["lease_id"]),
                    lease_expires_at=datetime.fromisoformat(str(body["lease_expires_at"])),
                )
            result = AgentWorkStore().renew_lease(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                now=command.now,
                lease_seconds=command.lease_seconds,
            )
            if checkpoint is not None:
                checkpoint("after_renew_store")
            response_json = json.dumps(
                {
                    "work_id": result.work_id,
                    "thread_id": result.thread_id,
                    "state": result.state,
                    "attempt_no": result.attempt_no,
                    "lease_id": result.lease_id,
                    "lease_expires_at": result.lease_expires_at.isoformat(),
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, "
                "resource_id, response_json) VALUES (?, 'renew', ?, ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    command.work_id,
                    response_json,
                ],
            )
            if checkpoint is not None:
                checkpoint("after_renew_receipt")
            return result


def _mark_agent_work_progress(
    db_path: str,
    command: MarkAcknowledgedCommand | MarkWorkingCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkProgress:
    command_kind = (
        "acknowledged" if isinstance(command, MarkAcknowledgedCommand) else "working"
    )
    request = {
        "attempt_no": command.attempt_no,
        "lease_id": command.lease_id,
        "logical_worker_id": command.logical_worker_id,
        "work_id": command.work_id,
    }
    if isinstance(command, MarkAcknowledgedCommand):
        request["transport_receipt_sha256"] = command.transport_receipt_sha256
    request_sha256 = hashlib.sha256(
        json.dumps(
            request,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with connect_write(db_path, purpose=f"agent_work/{command_kind}") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, response_json FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind=? AND idempotency_key=?",
                [
                    command.bridge_credential_id,
                    command_kind,
                    command.idempotency_key,
                ],
            ).fetchone()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                if receipt[1] is None:  # pragma: no cover - database invariant
                    raise RuntimeError(f"{command_kind} receipt has no canonical response")
                body = json.loads(str(receipt[1]))
                return WorkProgress(
                    work_id=str(body["work_id"]),
                    thread_id=str(body["thread_id"]),
                    state=str(body["state"]),
                    attempt_no=int(body["attempt_no"]),
                    lease_id=str(body["lease_id"]),
                    before_state=str(body["before_state"]),
                )
            domain_command = (
                MarkAcknowledged()
                if isinstance(command, MarkAcknowledgedCommand)
                else MarkWorking()
            )
            result = AgentWorkStore().mark_progress(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                now=command.now,
                command=domain_command,
                transport_receipt_sha256=(
                    command.transport_receipt_sha256
                    if isinstance(command, MarkAcknowledgedCommand)
                    else None
                ),
            )
            if checkpoint is not None:
                checkpoint(f"after_{command_kind}_store")
            investigation_id = str(
                con.execute(
                    "SELECT investigation_id FROM feedback_threads WHERE thread_id=?",
                    [result.thread_id],
                ).fetchone()[0]
            )
            transitioned = build_typed_envelope(
                investigation_id,
                AgentWorkTransitionedPayload(
                    work_id=result.work_id,
                    thread_id=result.thread_id,
                    before_state=result.before_state,
                    after_state=result.state,
                    attempt_no=result.attempt_no,
                    reason=f"bridge_{command_kind}",
                ),
                event_id=(
                    f"evt-agent-work-{command_kind}-{result.work_id}-{result.attempt_no}"
                ),
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=(
                    f"agent-transition:{result.work_id}:{result.attempt_no}:{command_kind}"
                ),
                aggregate_kind="agent_work",
                aggregate_id=result.work_id,
                event=transitioned,
            )
            if checkpoint is not None:
                checkpoint(f"after_{command_kind}_event")
            response_json = json.dumps(
                {
                    "work_id": result.work_id,
                    "thread_id": result.thread_id,
                    "state": result.state,
                    "attempt_no": result.attempt_no,
                    "lease_id": result.lease_id,
                    "before_state": result.before_state,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, "
                "resource_id, response_json) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command_kind,
                    command.idempotency_key,
                    request_sha256,
                    command.work_id,
                    response_json,
                ],
            )
            if checkpoint is not None:
                checkpoint(f"after_{command_kind}_receipt")
            return result


def mark_agent_work_acknowledged(
    db_path: str,
    command: MarkAcknowledgedCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkProgress:
    return _mark_agent_work_progress(db_path, command, checkpoint=checkpoint)


def mark_agent_work_working(
    db_path: str,
    command: MarkWorkingCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkProgress:
    return _mark_agent_work_progress(db_path, command, checkpoint=checkpoint)


def _submitted_request_sha256(command: MarkSubmittedCommand) -> str:
    canonical = json.dumps(
        {
            "adapter_version": command.adapter_version,
            "attempt_no": command.attempt_no,
            "herdr_target_observed": command.herdr_target_observed,
            "lease_id": command.lease_id,
            "logical_worker_id": command.logical_worker_id,
            "work_id": command.work_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mark_agent_work_submitted(
    db_path: str,
    command: MarkSubmittedCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkProgress:
    """Atomically record, audit, and exactly replay adapter submission."""
    request_sha256 = _submitted_request_sha256(command)
    with connect_write(db_path, purpose="agent_work/submitted") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id, response_json "
                "FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='submitted' AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            store = AgentWorkStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                if receipt[2] is not None:
                    body = json.loads(str(receipt[2]))
                    return WorkProgress(
                        work_id=str(body["work_id"]),
                        thread_id=str(body["thread_id"]),
                        state=str(body["state"]),
                        attempt_no=int(body["attempt_no"]),
                        lease_id=str(body["lease_id"]),
                        before_state=str(body["before_state"]),
                    )
                replay = store.get_progress(
                    con,
                    work_id=str(receipt[1]),
                    lease_id=command.lease_id,
                    attempt_no=command.attempt_no,
                    logical_worker_id=command.logical_worker_id,
                    bridge_credential_id=command.bridge_credential_id,
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("submitted receipt has no canonical result")
                return replay

            result = store.mark_submitted(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                now=command.now,
                adapter_version=command.adapter_version,
                herdr_target_observed=command.herdr_target_observed,
            )
            if checkpoint is not None:
                checkpoint("after_submitted_store")
            investigation_id = str(
                con.execute(
                    "SELECT investigation_id FROM feedback_threads WHERE thread_id=?",
                    [result.thread_id],
                ).fetchone()[0]
            )
            transitioned = build_typed_envelope(
                investigation_id,
                AgentWorkTransitionedPayload(
                    work_id=result.work_id,
                    thread_id=result.thread_id,
                    before_state="leased",
                    after_state=result.state,
                    attempt_no=result.attempt_no,
                    reason="adapter_submitted",
                ),
                event_id=f"evt-agent-work-submitted-{result.work_id}-{result.attempt_no}",
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=(
                    f"agent-transition:{result.work_id}:{result.attempt_no}:submitted"
                ),
                aggregate_kind="agent_work",
                aggregate_id=result.work_id,
                event=transitioned,
            )
            if checkpoint is not None:
                checkpoint("after_submitted_event")
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, "
                "resource_id, response_json) VALUES (?, 'submitted', ?, ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    result.work_id,
                    json.dumps(
                        {
                            "work_id": result.work_id,
                            "thread_id": result.thread_id,
                            "state": result.state,
                            "attempt_no": result.attempt_no,
                            "lease_id": result.lease_id,
                            "before_state": result.before_state,
                        },
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ],
            )
            if checkpoint is not None:
                checkpoint("after_submitted_receipt")
            return result


def _request_sha256(command: CompleteReplyCommand) -> str:
    canonical = json.dumps(
        {
            "agent_id": command.agent_id,
            "attempt_no": command.attempt_no,
            "context_sha256": command.context_sha256,
            "lease_id": command.lease_id,
            "logical_worker_id": command.logical_worker_id,
            "reply_item_id": command.reply_item_id,
            "reply_markdown": command.reply_markdown,
            "work_id": command.work_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def complete_agent_reply(
    db_path: str,
    command: CompleteReplyCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> ReplyCompletion:
    """Atomically append, audit, and exactly replay one agent reply."""
    request_sha256 = _request_sha256(command)
    with connect_write(db_path, purpose="agent_work/reply") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='complete_reply' AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            store = AgentWorkStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                replay = store.get_reply_completion(
                    con,
                    work_id=command.work_id,
                    logical_worker_id=command.logical_worker_id,
                    bridge_credential_id=command.bridge_credential_id,
                    reply_item_id=str(receipt[1]),
                    attempt_no=command.attempt_no,
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("reply receipt has no canonical result")
                return replay

            result = store.complete_with_reply(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                context_sha256=command.context_sha256,
                result_sha256=request_sha256,
                reply_item_id=command.reply_item_id,
                reply_markdown=command.reply_markdown,
                agent_id=command.agent_id,
                now=command.now,
            )
            if checkpoint is not None:
                checkpoint("after_reply")
            event = build_typed_envelope(
                result.thread.investigation_id,
                ArtifactFeedbackRepliedPayload(
                    work_id=command.work_id,
                    thread_id=result.thread.thread_id,
                    reply_item_id=command.reply_item_id,
                    attempt_no=command.attempt_no,
                    reply_sha256=hashlib.sha256(command.reply_markdown.encode("utf-8")).hexdigest(),
                ),
                event_id=f"evt-feedback-reply-{command.reply_item_id}",
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=f"agent-result:{command.work_id}:{command.attempt_no}",
                aggregate_kind="feedback_thread",
                aggregate_id=result.thread.thread_id,
                event=event,
            )
            if checkpoint is not None:
                checkpoint("after_reply_feedback_event")
            transitioned = build_typed_envelope(
                result.thread.investigation_id,
                AgentWorkTransitionedPayload(
                    work_id=command.work_id,
                    thread_id=result.thread.thread_id,
                    before_state=result.before_state,
                    after_state=result.state,
                    attempt_no=command.attempt_no,
                    reason="agent_reply",
                ),
                event_id=f"evt-agent-work-replied-{command.work_id}-{command.attempt_no}",
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=f"agent-transition:{command.work_id}:{command.attempt_no}:replied",
                aggregate_kind="agent_work",
                aggregate_id=command.work_id,
                event=transitioned,
            )
            if checkpoint is not None:
                checkpoint("after_reply_transition_event")
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, resource_id"
                ") VALUES (?, 'complete_reply', ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    command.reply_item_id,
                ],
            )
            if checkpoint is not None:
                checkpoint("after_receipt")
            return result


def complete_agent_failure(
    db_path: str,
    command: CompleteFailureCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> WorkProgress:
    """Atomically record one bounded retryable or terminal bridge failure."""
    request_sha256 = hashlib.sha256(
        json.dumps(
            {
                "attempt_no": command.attempt_no,
                "context_sha256": command.context_sha256,
                "error_code": command.error_code,
                "lease_id": command.lease_id,
                "logical_worker_id": command.logical_worker_id,
                "retryable": command.retryable,
                "work_id": command.work_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with connect_write(db_path, purpose="agent_work/failure") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, response_json FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='complete_failure' "
                "AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                if receipt[1] is None:  # pragma: no cover - database invariant
                    raise RuntimeError("failure receipt has no canonical response")
                body = json.loads(str(receipt[1]))
                return WorkProgress(
                    work_id=str(body["work_id"]),
                    thread_id=str(body["thread_id"]),
                    state=str(body["state"]),
                    attempt_no=int(body["attempt_no"]),
                    lease_id=str(body["lease_id"]),
                    before_state=str(body["before_state"]),
                )
            result = AgentWorkStore().complete_with_failure(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                context_sha256=command.context_sha256,
                result_sha256=request_sha256,
                error_code=command.error_code,
                retryable=command.retryable,
                now=command.now,
            )
            if checkpoint is not None:
                checkpoint("after_failure_store")
            investigation_id = str(
                con.execute(
                    "SELECT investigation_id FROM feedback_threads WHERE thread_id=?",
                    [result.thread_id],
                ).fetchone()[0]
            )
            reason = "retryable_failure" if result.state == "queued" else "failed"
            transitioned = build_typed_envelope(
                investigation_id,
                AgentWorkTransitionedPayload(
                    work_id=result.work_id,
                    thread_id=result.thread_id,
                    before_state=result.before_state,
                    after_state=result.state,
                    attempt_no=result.attempt_no,
                    reason=reason,
                ),
                event_id=(
                    f"evt-agent-work-{reason}-{result.work_id}-{result.attempt_no}"
                ),
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=(
                    f"agent-transition:{result.work_id}:{result.attempt_no}:{reason}"
                ),
                aggregate_kind="agent_work",
                aggregate_id=result.work_id,
                event=transitioned,
            )
            if checkpoint is not None:
                checkpoint("after_failure_event")
            response_json = json.dumps(
                {
                    "work_id": result.work_id,
                    "thread_id": result.thread_id,
                    "state": result.state,
                    "attempt_no": result.attempt_no,
                    "lease_id": result.lease_id,
                    "before_state": result.before_state,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, "
                "resource_id, response_json) VALUES (?, 'complete_failure', ?, ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    command.work_id,
                    response_json,
                ],
            )
            if checkpoint is not None:
                checkpoint("after_failure_receipt")
            return result


def complete_agent_disposition(
    db_path: str,
    command: CompleteDispositionCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> ReplyCompletion:
    """Append and audit one terminal decline or approval request."""
    if command.kind not in {"decline", "approval_request"}:
        raise ValueError("unsupported agent disposition")
    request_sha256 = hashlib.sha256(
        json.dumps(
            {
                "agent_id": command.agent_id,
                "attempt_no": command.attempt_no,
                "context_sha256": command.context_sha256,
                "kind": command.kind,
                "lease_id": command.lease_id,
                "logical_worker_id": command.logical_worker_id,
                "message_item_id": command.message_item_id,
                "message_markdown": command.message_markdown,
                "work_id": command.work_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    expected_state = "declined" if command.kind == "decline" else "approval_requested"
    result_kind = (
        ResultKind.DECLINE
        if command.kind == "decline"
        else ResultKind.APPROVAL_REQUEST
    )
    with connect_write(db_path, purpose="agent_work/disposition") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='complete_disposition' "
                "AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            store = AgentWorkStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                replay = store.get_reply_completion(
                    con,
                    work_id=command.work_id,
                    logical_worker_id=command.logical_worker_id,
                    bridge_credential_id=command.bridge_credential_id,
                    reply_item_id=str(receipt[1]),
                    attempt_no=command.attempt_no,
                    expected_state=expected_state,
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("disposition receipt has no canonical result")
                return replay
            result = store.complete_with_reply(
                con,
                work_id=command.work_id,
                lease_id=command.lease_id,
                attempt_no=command.attempt_no,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                context_sha256=command.context_sha256,
                result_sha256=request_sha256,
                reply_item_id=command.message_item_id,
                reply_markdown=command.message_markdown,
                agent_id=command.agent_id,
                now=command.now,
                result_kind=result_kind,
            )
            if checkpoint is not None:
                checkpoint("after_disposition_store")
            event = build_typed_envelope(
                result.thread.investigation_id,
                ArtifactFeedbackRepliedPayload(
                    work_id=command.work_id,
                    thread_id=result.thread.thread_id,
                    reply_item_id=command.message_item_id,
                    attempt_no=command.attempt_no,
                    reply_sha256=hashlib.sha256(
                        command.message_markdown.encode("utf-8")
                    ).hexdigest(),
                    result_kind=command.kind,
                ),
                event_id=f"evt-feedback-reply-{command.message_item_id}",
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=f"agent-result:{command.work_id}:{command.attempt_no}",
                aggregate_kind="feedback_thread",
                aggregate_id=result.thread.thread_id,
                event=event,
            )
            if checkpoint is not None:
                checkpoint("after_disposition_feedback_event")
            transitioned = build_typed_envelope(
                result.thread.investigation_id,
                AgentWorkTransitionedPayload(
                    work_id=command.work_id,
                    thread_id=result.thread.thread_id,
                    before_state=result.before_state,
                    after_state=result.state,
                    attempt_no=command.attempt_no,
                    reason=f"agent_{command.kind}",
                ),
                event_id=(
                    f"evt-agent-work-{result.state}-{command.work_id}-{command.attempt_no}"
                ),
                emitted_at=command.now,
            )
            enqueue_event(
                con,
                operation_id=(
                    f"agent-transition:{command.work_id}:{command.attempt_no}:"
                    f"{result.state}"
                ),
                aggregate_kind="agent_work",
                aggregate_id=command.work_id,
                event=transitioned,
            )
            if checkpoint is not None:
                checkpoint("after_disposition_transition_event")
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, resource_id"
                ") VALUES (?, 'complete_disposition', ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    command.message_item_id,
                ],
            )
            if checkpoint is not None:
                checkpoint("after_disposition_receipt")
            return result
