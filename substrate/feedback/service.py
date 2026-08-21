"""Transactional command boundary for artifact feedback."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from runtime.db_lock import LockedConnection, connect_write
from substrate.feedback.anchor import validate_artifact_anchor
from substrate.feedback.schema import init_feedback_schema
from substrate.feedback.store import CreateThreadCommand, FeedbackStore, ThreadView
from substrate.schemas.events import (
    AgentWorkTransitionedPayload,
    ArtifactCommentCreatedPayload,
    FeedbackThreadResolvedPayload,
)
from substrate.write.event_outbox import (
    build_typed_envelope,
    enqueue_event,
    event_for_operation,
    eventful_transaction,
)


def _persist_feedback_thread(
    con: LockedConnection,
    command: CreateThreadCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> ThreadView:
    """Persist a prevalidated command inside the caller's transaction."""
    thread = FeedbackStore().create_thread(con, command, checkpoint=checkpoint)
    comment_operation = f"{command.operation_id}:comment"
    if event_for_operation(con, comment_operation) is None:
        comment = build_typed_envelope(
            command.investigation_id,
            ArtifactCommentCreatedPayload(
                thread_id=command.thread_id,
                item_id=command.root_item_id,
                artifact_id=command.artifact.artifact_id,
                artifact_version=command.artifact.version,
                artifact_content_sha256=command.artifact.content_sha256,
                artifact_source_sha256=command.artifact.source_sha256,
                anchor_node_id=command.anchor.node_id,
                body_sha256=hashlib.sha256(command.body_markdown.encode("utf-8")).hexdigest(),
            ),
            event_id=f"evt-feedback-comment-{command.thread_id}",
        )
        enqueue_event(
            con,
            operation_id=comment_operation,
            aggregate_kind="feedback_thread",
            aggregate_id=command.thread_id,
            event=comment,
        )
    if checkpoint is not None:
        checkpoint("after_comment_event")

    work_operation = f"{command.operation_id}:work"
    if event_for_operation(con, work_operation) is None:
        queued = build_typed_envelope(
            command.investigation_id,
            AgentWorkTransitionedPayload(
                work_id=command.work_id,
                thread_id=command.thread_id,
                before_state=None,
                after_state="queued",
                attempt_no=0,
                reason="feedback_created",
            ),
            event_id=f"evt-agent-work-queued-{command.work_id}",
        )
        enqueue_event(
            con,
            operation_id=work_operation,
            aggregate_kind="agent_work",
            aggregate_id=command.work_id,
            event=queued,
        )
    if checkpoint is not None:
        checkpoint("after_work_event")
    return thread


def create_feedback_thread(
    db_path: str,
    command: CreateThreadCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> ThreadView:
    """Commit an already validated command (internal orchestration seam)."""
    with connect_write(db_path, purpose="feedback/create") as con:  # noqa: SIM117
        with eventful_transaction(con, command.investigation_id):
            return _persist_feedback_thread(con, command, checkpoint=checkpoint)


def create_artifact_feedback(
    db_path: str,
    command: CreateThreadCommand,
    *,
    checkpoint: Callable[[str], None] | None = None,
) -> ThreadView:
    """Validate immutable ownership/bytes/node anchor, then commit feedback."""
    with connect_write(db_path, purpose="feedback/create_validated") as con:  # noqa: SIM117
        with eventful_transaction(con, command.investigation_id):
            validated = validate_artifact_anchor(
                con,
                owner_user_id=command.owner_user_id,
                artifact=command.artifact,
                anchor=command.anchor,
            )
            if validated.investigation_id != command.investigation_id:
                raise ValueError("artifact does not belong to the investigation")
            return _persist_feedback_thread(con, command, checkpoint=checkpoint)


@dataclass(frozen=True, slots=True)
class ResolveThreadCommand:
    owner_user_id: str
    thread_id: str
    idempotency_key: str


def resolve_feedback_thread(db_path: str, command: ResolveThreadCommand) -> ThreadView:
    """Atomically resolve, audit, and exactly replay one feedback thread."""
    request_sha256 = hashlib.sha256(
        json.dumps(
            {
                "owner_user_id": command.owner_user_id,
                "thread_id": command.thread_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    with connect_write(db_path, purpose="feedback/resolve") as con:  # noqa: SIM117
        with eventful_transaction(con, "unused-until-thread-load"):
            init_feedback_schema(con)
            receipt = con.execute(
                "SELECT request_sha256, resource_id FROM feedback_command_receipts "
                "WHERE principal_id=? AND command_kind='resolve_thread' "
                "AND idempotency_key=?",
                [command.owner_user_id, command.idempotency_key],
            ).fetchone()
            store = FeedbackStore()
            if receipt is not None:
                if str(receipt[0]) != request_sha256:
                    raise ValueError("idempotency key was reused with different bytes")
                replay = store.get_thread(
                    con,
                    owner_user_id=command.owner_user_id,
                    thread_id=str(receipt[1]),
                )
                if replay is None:  # pragma: no cover - database invariant
                    raise RuntimeError("resolve receipt has no canonical result")
                return replay
            thread = store.resolve_thread(
                con,
                owner_user_id=command.owner_user_id,
                thread_id=command.thread_id,
            )
            operation_id = f"feedback-resolve:{thread.thread_id}"
            if event_for_operation(con, operation_id) is None:
                event = build_typed_envelope(
                    thread.investigation_id,
                    FeedbackThreadResolvedPayload(
                        thread_id=thread.thread_id,
                        artifact_id=thread.artifact.artifact_id,
                        artifact_version=thread.artifact.version,
                    ),
                    event_id=f"evt-feedback-resolved-{thread.thread_id}",
                )
                enqueue_event(
                    con,
                    operation_id=operation_id,
                    aggregate_kind="feedback_thread",
                    aggregate_id=thread.thread_id,
                    event=event,
                )
            con.execute(
                "INSERT INTO feedback_command_receipts ("
                "principal_id, command_kind, idempotency_key, request_sha256, resource_id"
                ") VALUES (?, 'resolve_thread', ?, ?, ?)",
                [
                    command.owner_user_id,
                    command.idempotency_key,
                    request_sha256,
                    thread.thread_id,
                ],
            )
            return thread
