"""Connection-taking persistence for feedback aggregates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.schema import init_feedback_schema


class IdempotencyConflict(ValueError):
    """An operation identity was reused for different canonical bytes."""


@dataclass(frozen=True, slots=True)
class CreateThreadCommand:
    thread_id: str
    root_item_id: str
    work_id: str
    owner_user_id: str
    investigation_id: str
    logical_worker_id: str
    artifact: ArtifactVersionRef
    anchor: NodeTextAnchor
    body_markdown: str
    operation_id: str
    request_sha256: str
    context_sha256: str


@dataclass(frozen=True, slots=True)
class FeedbackItemView:
    item_id: str
    author_kind: str
    author_id: str
    body_markdown: str
    sequence: int


@dataclass(frozen=True, slots=True)
class WorkView:
    work_id: str
    logical_worker_id: str
    state: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ThreadView:
    thread_id: str
    investigation_id: str
    state: str
    artifact: ArtifactVersionRef
    anchor: NodeTextAnchor
    items: tuple[FeedbackItemView, ...]
    work: WorkView


class FeedbackStore:
    """Persist and read one-thread/one-work feedback aggregates."""

    def create_thread(
        self,
        con: LockedConnection,
        command: CreateThreadCommand,
        *,
        checkpoint: Callable[[str], None] | None = None,
    ) -> ThreadView:
        init_feedback_schema(con)
        prior = con.execute(
            "SELECT thread_id, owner_user_id, create_request_sha256 "
            "FROM feedback_threads WHERE create_operation_id=?",
            [command.operation_id],
        ).fetchone()
        if prior is not None:
            if str(prior[1]) != command.owner_user_id or str(prior[2]) != command.request_sha256:
                raise IdempotencyConflict("operation identity was reused with different bytes")
            replay = self.get_thread(
                con,
                owner_user_id=command.owner_user_id,
                thread_id=str(prior[0]),
            )
            if replay is None:  # pragma: no cover - database invariant
                raise RuntimeError("idempotent feedback thread could not be read back")
            return replay
        anchor = command.anchor
        artifact = command.artifact
        con.execute(
            "INSERT INTO feedback_threads ("
            "thread_id, owner_user_id, investigation_id, artifact_id, artifact_version, "
            "artifact_content_sha256, artifact_source_sha256, normalization, anchor_node_id, "
            "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, anchor_quote, "
            "anchor_prefix, anchor_suffix, create_operation_id, create_request_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                command.thread_id,
                command.owner_user_id,
                command.investigation_id,
                artifact.artifact_id,
                artifact.version,
                artifact.content_sha256,
                artifact.source_sha256,
                anchor.normalization,
                anchor.node_id,
                anchor.node_text_sha256,
                anchor.start_scalar,
                anchor.end_scalar,
                anchor.quote,
                anchor.prefix,
                anchor.suffix,
                command.operation_id,
                command.request_sha256,
            ],
        )
        if checkpoint is not None:
            checkpoint("after_thread")
        con.execute(
            "INSERT INTO agent_work (work_id, thread_id, logical_worker_id, context_sha256) "
            "VALUES (?, ?, ?, ?)",
            [
                command.work_id,
                command.thread_id,
                command.logical_worker_id,
                command.context_sha256,
            ],
        )
        if checkpoint is not None:
            checkpoint("after_work")
        con.execute(
            "INSERT INTO feedback_items ("
            "item_id, thread_id, sequence, author_kind, author_id, body_markdown"
            ") VALUES (?, ?, 1, 'operator', ?, ?)",
            [
                command.root_item_id,
                command.thread_id,
                command.owner_user_id,
                command.body_markdown,
            ],
        )
        if checkpoint is not None:
            checkpoint("after_root_item")
        loaded = self.get_thread(
            con,
            owner_user_id=command.owner_user_id,
            thread_id=command.thread_id,
        )
        if loaded is None:  # pragma: no cover - database invariant
            raise RuntimeError("created feedback thread could not be read back")
        return loaded

    def get_thread(
        self, con: LockedConnection, *, owner_user_id: str, thread_id: str
    ) -> ThreadView | None:
        init_feedback_schema(con)
        row = con.execute(
            "SELECT investigation_id, state, artifact_id, artifact_version, "
            "artifact_content_sha256, artifact_source_sha256, normalization, anchor_node_id, "
            "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, anchor_quote, "
            "anchor_prefix, anchor_suffix FROM feedback_threads "
            "WHERE thread_id=? AND owner_user_id=?",
            [thread_id, owner_user_id],
        ).fetchone()
        if row is None:
            return None
        item_rows = con.execute(
            "SELECT item_id, author_kind, author_id, body_markdown, sequence "
            "FROM feedback_items WHERE thread_id=? ORDER BY sequence",
            [thread_id],
        ).fetchall()
        work_row = con.execute(
            "SELECT work_id, logical_worker_id, state, attempt_count "
            "FROM agent_work WHERE thread_id=?",
            [thread_id],
        ).fetchone()
        if work_row is None:  # pragma: no cover - database invariant
            raise RuntimeError("feedback thread has no work item")
        return ThreadView(
            thread_id=thread_id,
            investigation_id=str(row[0]),
            state=str(row[1]),
            artifact=ArtifactVersionRef(str(row[2]), int(row[3]), str(row[4]), str(row[5])),
            anchor=NodeTextAnchor(
                node_id=str(row[7]),
                node_text_sha256=str(row[8]),
                start_scalar=int(row[9]),
                end_scalar=int(row[10]),
                quote=str(row[11]),
                prefix=str(row[12]),
                suffix=str(row[13]),
                normalization=str(row[6]),
            ),
            items=tuple(
                FeedbackItemView(
                    str(item[0]), str(item[1]), str(item[2]), str(item[3]), int(item[4])
                )
                for item in item_rows
            ),
            work=WorkView(str(work_row[0]), str(work_row[1]), str(work_row[2]), int(work_row[3])),
        )
