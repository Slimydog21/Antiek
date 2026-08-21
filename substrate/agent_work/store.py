"""Single-writer persistence for leasing canonical agent work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from runtime.db_lock import LockedConnection
from substrate.agent_work.domain import (
    FinishWork,
    MarkSubmitted,
    ResultKind,
    WorkState,
    decide_transition,
)
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.schema import init_feedback_schema
from substrate.feedback.store import FeedbackStore, ThreadView


class LeaseConflict(ValueError):
    """The command does not hold the current, unexpired work lease."""


@dataclass(frozen=True, slots=True)
class WorkLease:
    work_id: str
    thread_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    lease_expires_at: datetime
    artifact: ArtifactVersionRef
    anchor: NodeTextAnchor
    comment_markdown: str
    context_sha256: str


@dataclass(frozen=True, slots=True)
class WorkProgress:
    work_id: str
    thread_id: str
    state: str
    attempt_no: int
    lease_id: str


@dataclass(frozen=True, slots=True)
class ReplyCompletion:
    state: str
    before_state: str
    reply_item_id: str
    thread: ThreadView


class AgentWorkStore:
    """Lease queued work under Antiek's existing global writer lock."""

    def lease_one(
        self,
        con: LockedConnection,
        *,
        logical_worker_id: str,
        bridge_credential_id: str,
        bridge_instance_id: str,
        lease_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> WorkLease | None:
        if not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        init_feedback_schema(con)
        row = con.execute(
            "SELECT w.work_id, w.thread_id, w.attempt_count, w.context_sha256, "
            "t.artifact_id, t.artifact_version, t.artifact_content_sha256, "
            "t.artifact_source_sha256, t.normalization, t.anchor_node_id, "
            "t.anchor_node_text_sha256, t.anchor_start_scalar, t.anchor_end_scalar, "
            "t.anchor_quote, t.anchor_prefix, t.anchor_suffix, i.body_markdown "
            "FROM agent_work w "
            "JOIN feedback_threads t ON t.thread_id=w.thread_id "
            "JOIN feedback_items i ON i.thread_id=t.thread_id AND i.sequence=1 "
            "WHERE w.logical_worker_id=? AND w.state='queued' AND w.not_before<=? "
            "ORDER BY w.created_at, w.work_id LIMIT 1",
            [logical_worker_id, now],
        ).fetchone()
        if row is None:
            return None

        work_id = str(row[0])
        thread_id = str(row[1])
        attempt_no = int(row[2]) + 1
        expires_at = now + timedelta(seconds=lease_seconds)
        changed = con.execute(
            "UPDATE agent_work SET state='leased', attempt_count=?, active_lease_id=?, "
            "lease_expires_at=?, updated_at=? WHERE work_id=? AND state='queued' "
            "RETURNING work_id",
            [attempt_no, lease_id, expires_at, now, work_id],
        ).fetchone()
        if changed is None:  # pragma: no cover - global writer invariant
            return None
        con.execute(
            "INSERT INTO agent_work_attempts ("
            "attempt_id, work_id, attempt_no, lease_id, bridge_credential_id, "
            "bridge_instance_id, lease_expires_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                f"attempt:{work_id}:{attempt_no}",
                work_id,
                attempt_no,
                lease_id,
                bridge_credential_id,
                bridge_instance_id,
                expires_at,
            ],
        )
        return WorkLease(
            work_id=work_id,
            thread_id=thread_id,
            lease_id=lease_id,
            attempt_no=attempt_no,
            logical_worker_id=logical_worker_id,
            lease_expires_at=expires_at,
            artifact=ArtifactVersionRef(str(row[4]), int(row[5]), str(row[6]), str(row[7])),
            anchor=NodeTextAnchor(
                node_id=str(row[9]),
                node_text_sha256=str(row[10]),
                start_scalar=int(row[11]),
                end_scalar=int(row[12]),
                quote=str(row[13]),
                prefix=str(row[14]),
                suffix=str(row[15]),
                normalization=str(row[8]),
            ),
            comment_markdown=str(row[16]),
            context_sha256=str(row[3]),
        )

    def get_lease(
        self,
        con: LockedConnection,
        *,
        logical_worker_id: str,
        lease_id: str,
    ) -> WorkLease | None:
        """Read the canonical work context for an already issued lease."""
        init_feedback_schema(con)
        row = con.execute(
            "SELECT w.work_id, w.thread_id, a.attempt_no, w.context_sha256, "
            "t.artifact_id, t.artifact_version, t.artifact_content_sha256, "
            "t.artifact_source_sha256, t.normalization, t.anchor_node_id, "
            "t.anchor_node_text_sha256, t.anchor_start_scalar, t.anchor_end_scalar, "
            "t.anchor_quote, t.anchor_prefix, t.anchor_suffix, i.body_markdown, "
            "a.lease_expires_at "
            "FROM agent_work w "
            "JOIN agent_work_attempts a ON a.work_id=w.work_id "
            "JOIN feedback_threads t ON t.thread_id=w.thread_id "
            "JOIN feedback_items i ON i.thread_id=t.thread_id AND i.sequence=1 "
            "WHERE w.logical_worker_id=? AND a.lease_id=?",
            [logical_worker_id, lease_id],
        ).fetchone()
        if row is None:
            return None
        return WorkLease(
            work_id=str(row[0]),
            thread_id=str(row[1]),
            lease_id=lease_id,
            attempt_no=int(row[2]),
            logical_worker_id=logical_worker_id,
            lease_expires_at=row[17],
            artifact=ArtifactVersionRef(str(row[4]), int(row[5]), str(row[6]), str(row[7])),
            anchor=NodeTextAnchor(
                node_id=str(row[9]),
                node_text_sha256=str(row[10]),
                start_scalar=int(row[11]),
                end_scalar=int(row[12]),
                quote=str(row[13]),
                prefix=str(row[14]),
                suffix=str(row[15]),
                normalization=str(row[8]),
            ),
            comment_markdown=str(row[16]),
            context_sha256=str(row[3]),
        )

    def mark_submitted(
        self,
        con: LockedConnection,
        *,
        work_id: str,
        lease_id: str,
        attempt_no: int,
        logical_worker_id: str,
        now: datetime,
        adapter_version: str,
        herdr_target_observed: str,
    ) -> WorkProgress:
        """Record adapter submission only for the current live lease."""
        init_feedback_schema(con)
        row = con.execute(
            "SELECT thread_id, state, attempt_count FROM agent_work "
            "WHERE work_id=? AND logical_worker_id=? AND active_lease_id=? "
            "AND attempt_count=? AND lease_expires_at>?",
            [work_id, logical_worker_id, lease_id, attempt_no, now],
        ).fetchone()
        if row is None:
            raise LeaseConflict("work lease is missing, expired, or superseded")
        transition = decide_transition(WorkState(str(row[1])), MarkSubmitted())
        changed = con.execute(
            "UPDATE agent_work SET state=?, updated_at=? "
            "WHERE work_id=? AND state=? AND active_lease_id=? RETURNING work_id",
            [transition.after.value, now, work_id, transition.before.value, lease_id],
        ).fetchone()
        if changed is None:  # pragma: no cover - global writer invariant
            raise LeaseConflict("work lease changed during submission")
        con.execute(
            "UPDATE agent_work_attempts SET state='submitted', adapter_version=?, "
            "herdr_target_observed=?, submitted_at=? "
            "WHERE work_id=? AND attempt_no=? AND lease_id=?",
            [adapter_version, herdr_target_observed, now, work_id, attempt_no, lease_id],
        )
        return WorkProgress(
            work_id=work_id,
            thread_id=str(row[0]),
            state=transition.after.value,
            attempt_no=attempt_no,
            lease_id=lease_id,
        )

    def get_progress(
        self,
        con: LockedConnection,
        *,
        work_id: str,
        lease_id: str,
        attempt_no: int,
        logical_worker_id: str,
    ) -> WorkProgress | None:
        """Read progress for one canonical work attempt."""
        init_feedback_schema(con)
        row = con.execute(
            "SELECT w.thread_id, w.state FROM agent_work w "
            "JOIN agent_work_attempts a ON a.work_id=w.work_id "
            "WHERE w.work_id=? AND w.logical_worker_id=? "
            "AND a.lease_id=? AND a.attempt_no=?",
            [work_id, logical_worker_id, lease_id, attempt_no],
        ).fetchone()
        if row is None:
            return None
        return WorkProgress(
            work_id=work_id,
            thread_id=str(row[0]),
            state=str(row[1]),
            attempt_no=attempt_no,
            lease_id=lease_id,
        )

    def complete_with_reply(
        self,
        con: LockedConnection,
        *,
        work_id: str,
        lease_id: str,
        attempt_no: int,
        logical_worker_id: str,
        context_sha256: str,
        result_sha256: str,
        reply_item_id: str,
        reply_markdown: str,
        agent_id: str,
        now: datetime,
    ) -> ReplyCompletion:
        """Append one correlated reply and terminally complete its work."""
        init_feedback_schema(con)
        row = con.execute(
            "SELECT w.thread_id, w.state, t.owner_user_id "
            "FROM agent_work w JOIN feedback_threads t ON t.thread_id=w.thread_id "
            "WHERE w.work_id=? AND w.logical_worker_id=? AND w.active_lease_id=? "
            "AND w.attempt_count=? AND w.context_sha256=? AND w.lease_expires_at>?",
            [work_id, logical_worker_id, lease_id, attempt_no, context_sha256, now],
        ).fetchone()
        if row is None:
            raise LeaseConflict("work lease is missing, expired, or superseded")
        transition = decide_transition(
            WorkState(str(row[1])),
            FinishWork(kind=ResultKind.REPLY, attempt_no=attempt_no),
        )
        thread_id = str(row[0])
        sequence = int(
            con.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM feedback_items WHERE thread_id=?",
                [thread_id],
            ).fetchone()[0]
        )
        con.execute(
            "INSERT INTO feedback_items ("
            "item_id, thread_id, sequence, author_kind, author_id, body_markdown, work_id"
            ") VALUES (?, ?, ?, 'agent', ?, ?, ?)",
            [reply_item_id, thread_id, sequence, agent_id, reply_markdown, work_id],
        )
        changed = con.execute(
            "UPDATE agent_work SET state=?, result_sha256=?, active_lease_id=NULL, "
            "lease_expires_at=NULL, updated_at=?, terminal_at=? "
            "WHERE work_id=? AND state=? AND active_lease_id=? RETURNING work_id",
            [
                transition.after.value,
                result_sha256,
                now,
                now,
                work_id,
                transition.before.value,
                lease_id,
            ],
        ).fetchone()
        if changed is None:  # pragma: no cover - global writer invariant
            raise LeaseConflict("work lease changed during reply completion")
        con.execute(
            "UPDATE agent_work_attempts SET state='completed', result_from_state=?, completed_at=? "
            "WHERE work_id=? AND attempt_no=? AND lease_id=?",
            [transition.before.value, now, work_id, attempt_no, lease_id],
        )
        thread = FeedbackStore().get_thread(
            con,
            owner_user_id=str(row[2]),
            thread_id=thread_id,
        )
        if thread is None:  # pragma: no cover - database invariant
            raise RuntimeError("completed feedback thread could not be read back")
        return ReplyCompletion(
            state=transition.after.value,
            before_state=transition.before.value,
            reply_item_id=reply_item_id,
            thread=thread,
        )

    def get_reply_completion(
        self,
        con: LockedConnection,
        *,
        work_id: str,
        logical_worker_id: str,
        reply_item_id: str,
    ) -> ReplyCompletion | None:
        """Read a previously committed reply for command replay."""
        init_feedback_schema(con)
        row = con.execute(
            "SELECT w.thread_id, w.state, t.owner_user_id, a.result_from_state "
            "FROM agent_work w JOIN feedback_threads t ON t.thread_id=w.thread_id "
            "JOIN agent_work_attempts a ON a.work_id=w.work_id "
            "WHERE w.work_id=? AND w.logical_worker_id=? AND w.state='replied'",
            [work_id, logical_worker_id],
        ).fetchone()
        if row is None:
            return None
        item = con.execute(
            "SELECT item_id FROM feedback_items "
            "WHERE item_id=? AND thread_id=? AND work_id=? AND author_kind='agent'",
            [reply_item_id, str(row[0]), work_id],
        ).fetchone()
        if item is None:
            return None
        thread = FeedbackStore().get_thread(
            con,
            owner_user_id=str(row[2]),
            thread_id=str(row[0]),
        )
        if thread is None:  # pragma: no cover - database invariant
            raise RuntimeError("replied feedback thread could not be read back")
        return ReplyCompletion(
            state=str(row[1]),
            before_state=str(row[3]),
            reply_item_id=str(item[0]),
            thread=thread,
        )
