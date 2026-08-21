"""Transactional command boundary for artifact feedback."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from runtime.db_lock import LockedConnection, connect_write
from substrate.feedback.anchor import validate_artifact_anchor
from substrate.feedback.store import CreateThreadCommand, FeedbackStore, ThreadView
from substrate.schemas.events import (
    AgentWorkTransitionedPayload,
    ArtifactCommentCreatedPayload,
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
