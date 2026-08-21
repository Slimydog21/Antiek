"""Transactional, idempotent commands for bridge-delivered agent work."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from runtime.db_lock import connect_write
from substrate.agent_work.store import AgentWorkStore, ReplyCompletion
from substrate.feedback.schema import init_feedback_schema
from substrate.schemas.events import ArtifactFeedbackRepliedPayload
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
    reply_item_id: str
    reply_markdown: str
    agent_id: str
    idempotency_key: str
    now: datetime


def _request_sha256(command: CompleteReplyCommand) -> str:
    canonical = json.dumps(
        {
            "agent_id": command.agent_id,
            "attempt_no": command.attempt_no,
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
