"""Rollback/atomicity tests for the v41 resolved-payload outbox path.

A rolled-back feedback transaction must leave neither an outbox event nor a
mutated row; a committed one must carry the full v41 tuple atomically.
"""

from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.feedback.store import FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    FeedbackThreadResolvedPayload,
)
from substrate.write.event_outbox import (
    EventOutboxError,
    build_typed_envelope,
    enqueue_event,
    event_for_operation,
    eventful_transaction,
)
from tests.test_feedback_store import _command


def _seed(db_path: str) -> None:
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="test/rollback-seed") as con:
        FeedbackStore().create_thread(con, _command())


def _resolved_payload(thread_id: str = "fth-1") -> FeedbackThreadResolvedPayload:
    return FeedbackThreadResolvedPayload(
        thread_id=thread_id,
        owner_user_id="owner-1",
        artifact_id="artifact-1",
        artifact_version=2,
        artifact_content_sha256="a" * 64,
        artifact_source_sha256="b" * 64,
        resolution_event_id=f"evt-feedback-resolved-{thread_id}",
    )


def test_rollback_leaves_no_event_and_no_mutation(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    _seed(db_path)
    operation_id = "feedback-resolve:fth-1"

    def failing_flow(con) -> None:
        with eventful_transaction(con, "inv-1"):
            store = FeedbackStore()
            store.resolve_thread(con, owner_user_id="owner-1", thread_id="fth-1")
            event = build_typed_envelope(
                "inv-1",
                _resolved_payload(),
                event_id="evt-feedback-resolved-fth-1",
            )
            enqueue_event(
                con,
                operation_id=operation_id,
                aggregate_kind="feedback_thread",
                aggregate_id="fth-1",
                event=event,
            )
            raise RuntimeError("synthetic failure")

    with (
        pytest.raises(RuntimeError, match="synthetic failure"),
        connect_write(db_path, purpose="test/rollback") as con,
    ):
        failing_flow(con)

    with connect_write(db_path, purpose="test/rollback-verify") as con:
        assert event_for_operation(con, operation_id) is None
        assert con.execute(
            "SELECT count(*) FROM write_event_outbox WHERE operation_id = ?",
            [operation_id],
        ).fetchone()[0] == 0
        thread = FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1")
    assert thread is not None
    assert thread.state == "open"


def test_commit_carries_v41_event_atomically(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    _seed(db_path)
    operation_id = "feedback-resolve:fth-1"

    def committing_flow(con) -> None:
        with eventful_transaction(con, "inv-1"):
            store = FeedbackStore()
            store.resolve_thread(con, owner_user_id="owner-1", thread_id="fth-1")
            enqueue_event(
                con,
                operation_id=operation_id,
                aggregate_kind="feedback_thread",
                aggregate_id="fth-1",
                event=build_typed_envelope(
                    "inv-1",
                    _resolved_payload(),
                    event_id="evt-feedback-resolved-fth-1",
                ),
            )

    with connect_write(db_path, purpose="test/commit") as con:
        committing_flow(con)

    with connect_write(db_path, purpose="test/commit-verify") as con:
        thread = FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1")
        event = event_for_operation(con, operation_id)
    assert thread is not None and thread.state == "resolved"
    assert event is not None
    assert event.schema_version == EVENT_SCHEMA_VERSION == 41
    payload = event.payload
    assert isinstance(payload, FeedbackThreadResolvedPayload)
    assert payload.resolution_event_id == "evt-feedback-resolved-fth-1"
    assert payload.owner_user_id == "owner-1"


def test_outbox_replay_rejects_byte_drift(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    _seed(db_path)
    operation_id = "feedback-resolve:fth-1"

    with connect_write(db_path, purpose="test/drift") as con:
        enqueue_event(
            con,
            operation_id=operation_id,
            aggregate_kind="feedback_thread",
            aggregate_id="fth-1",
            event=build_typed_envelope(
                "inv-1", _resolved_payload(), event_id="evt-feedback-resolved-fth-1"
            ),
        )
        with pytest.raises(EventOutboxError):
            enqueue_event(
                con,
                operation_id=operation_id,
                aggregate_kind="feedback_thread",
                aggregate_id="fth-1",
                event=build_typed_envelope(
                    "inv-1",
                    _resolved_payload(),
                    event_id="evt-feedback-resolved-fth-1",
                    role="other",
                ),
            )
