"""Transactional, idempotent commands for bridge-delivered agent work."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from runtime.db_lock import connect_write
from substrate.agent_work.store import AgentWorkStore, ReplyCompletion, WorkLease, WorkProgress
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


def lease_agent_work(db_path: str, command: LeaseWorkCommand) -> WorkLease | None:
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
                    lease_id=str(receipt[1]),
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("lease receipt has no canonical result")
                return replay

            lease = store.lease_one(
                con,
                logical_worker_id=command.logical_worker_id,
                bridge_credential_id=command.bridge_credential_id,
                bridge_instance_id=command.bridge_instance_id,
                lease_id=command.lease_id,
                now=command.now,
                lease_seconds=command.lease_seconds,
            )
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
            return lease


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
) -> WorkProgress:
    """Atomically record, audit, and exactly replay adapter submission."""
    request_sha256 = _submitted_request_sha256(command)
    with connect_write(db_path, purpose="agent_work/submitted") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-work-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='submitted' AND idempotency_key=?",
                [command.bridge_credential_id, command.idempotency_key],
            ).fetchone()
            store = AgentWorkStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                replay = store.get_progress(
                    con,
                    work_id=str(receipt[1]),
                    lease_id=command.lease_id,
                    attempt_no=command.attempt_no,
                    logical_worker_id=command.logical_worker_id,
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
                now=command.now,
                adapter_version=command.adapter_version,
                herdr_target_observed=command.herdr_target_observed,
            )
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
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, resource_id"
                ") VALUES (?, 'submitted', ?, ?, ?)",
                [
                    command.bridge_credential_id,
                    command.idempotency_key,
                    request_sha256,
                    result.work_id,
                ],
            )
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
                    reply_item_id=str(receipt[1]),
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
                checkpoint("after_reply_event")
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
