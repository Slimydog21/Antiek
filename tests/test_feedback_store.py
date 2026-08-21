from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand, FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.write.event_outbox import event_for_operation


def _command() -> CreateThreadCommand:
    return CreateThreadCommand(
        thread_id="fth-1",
        root_item_id="fit-1",
        work_id="wrk-1",
        owner_user_id="owner-1",
        investigation_id="inv-1",
        logical_worker_id="research-owner",
        artifact=ArtifactVersionRef(
            artifact_id="artifact-1",
            version=2,
            content_sha256="a" * 64,
            source_sha256="b" * 64,
        ),
        anchor=NodeTextAnchor(
            node_id="insight-1",
            node_text_sha256="c" * 64,
            start_scalar=0,
            end_scalar=4,
            quote="fact",
            prefix="",
            suffix=" remains",
        ),
        body_markdown="Please verify this against the primary paper.",
        operation_id="feedback:create:op-1",
        request_sha256="d" * 64,
        context_sha256="e" * 64,
    )


def test_create_thread_persists_root_comment_and_queued_work(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="test/feedback-create") as con:
        store = FeedbackStore()
        created = store.create_thread(con, _command())
        loaded = store.get_thread(con, owner_user_id="owner-1", thread_id="fth-1")

    assert created == loaded
    assert loaded is not None
    assert loaded.thread_id == "fth-1"
    assert loaded.state == "open"
    assert [item.body_markdown for item in loaded.items] == [
        "Please verify this against the primary paper."
    ]
    assert loaded.work.work_id == "wrk-1"
    assert loaded.work.state == "queued"
    assert loaded.artifact.version == 2


def test_create_thread_replays_same_operation_without_duplicate_rows(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="test/feedback-replay") as con:
        store = FeedbackStore()
        first = store.create_thread(con, _command())
        replay = store.create_thread(con, _command())

    assert replay == first
    assert len(replay.items) == 1


def test_create_command_rolls_back_every_row_when_work_insert_fails(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)

    def fail_after_thread(boundary: str) -> None:
        if boundary == "after_thread":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        create_feedback_thread(db_path, _command(), checkpoint=fail_after_thread)

    with connect_write(db_path, purpose="test/feedback-rollback-read") as con:
        assert FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1") is None


def test_create_command_enqueues_comment_and_work_events_atomically(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)

    create_feedback_thread(db_path, _command())

    with connect_write(db_path, purpose="test/feedback-events") as con:
        comment = event_for_operation(con, "feedback:create:op-1:comment")
        queued = event_for_operation(con, "feedback:create:op-1:work")

    assert comment is not None
    assert comment.action_type == "artifact.comment.created"
    assert comment.payload.thread_id == "fth-1"
    assert queued is not None
    assert queued.action_type == "agent.work.transitioned"
    assert queued.payload.before_state is None
    assert queued.payload.after_state == "queued"


def test_create_command_rolls_back_domain_and_outbox_after_first_event(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)

    def fail_after_comment_event(boundary: str) -> None:
        if boundary == "after_comment_event":
            raise RuntimeError("event boundary failure")

    with pytest.raises(RuntimeError, match="event boundary failure"):
        create_feedback_thread(db_path, _command(), checkpoint=fail_after_comment_event)

    with connect_write(db_path, purpose="test/feedback-event-rollback") as con:
        assert FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1") is None
        assert event_for_operation(con, "feedback:create:op-1:comment") is None
        assert event_for_operation(con, "feedback:create:op-1:work") is None
