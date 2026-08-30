"""Rollback/atomicity tests for the v41 resolved-payload outbox path.

A rolled-back feedback transaction must leave neither an outbox event nor a
mutated row; a committed one must carry the full v41 tuple atomically.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from runtime.db_lock import connect_write
from substrate.constants import ANTIEK_PARAM_VERSION
from substrate.feedback.service import ResolveThreadCommand, resolve_feedback_thread
from substrate.feedback.store import FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import (
    DEFAULT_POLICY_ID,
    EVENT_SCHEMA_VERSION,
    ArtifactCommentCreatedPayload,
    FeedbackThreadResolvedPayload,
    FeedbackThreadResolvedPayloadV40,
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


def test_resolve_rejects_existing_operation_with_wrong_event_identity(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    _seed(db_path)
    operation_id = "feedback-resolve:fth-1"

    wrong_event = build_typed_envelope(
        "inv-1",
        ArtifactCommentCreatedPayload(
            thread_id="fth-1",
            item_id="fit-1",
            artifact_id="artifact-1",
            artifact_version=2,
            artifact_content_sha256="a" * 64,
            artifact_source_sha256="b" * 64,
            anchor_node_id="insight-1",
            body_sha256="c" * 64,
        ),
        event_id="wrong-event",
    )
    with connect_write(db_path, purpose="test/wrong-resolution-event-seed") as con:
        enqueue_event(
            con,
            operation_id=operation_id,
            aggregate_kind="feedback_thread",
            aggregate_id="fth-1",
            event=wrong_event,
        )

    with pytest.raises(EventOutboxError, match="identity"):
        resolve_feedback_thread(
            db_path,
            ResolveThreadCommand(
                owner_user_id="owner-1",
                thread_id="fth-1",
                idempotency_key="resolve-key-wrong-event",
            ),
        )

    with connect_write(db_path, purpose="test/wrong-resolution-event-verify") as con:
        thread = FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1")
        receipt_count = con.execute(
            "SELECT count(*) FROM feedback_command_receipts "
            "WHERE principal_id='owner-1' AND command_kind='resolve_thread' "
            "AND idempotency_key='resolve-key-wrong-event'"
        ).fetchone()[0]
    assert thread is not None and thread.state == "open"
    assert receipt_count == 0


def test_v40_resolution_replays_through_read_only_adapter_without_reemit(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    _seed(db_path)
    operation_id = "feedback-resolve:fth-1"
    legacy_event = {
        "event_id": "evt-feedback-resolved-fth-1",
        "investigation_id": "inv-1",
        "synthesis_id": None,
        "phase": None,
        "role": None,
        "action_type": "feedback.thread.resolved",
        "payload": {
            "action_type": "feedback.thread.resolved",
            "thread_id": "fth-1",
            "artifact_id": "artifact-1",
            "artifact_version": 2,
            "reason": "operator_resolved",
        },
        "parent_event_id": None,
        "policy_id": DEFAULT_POLICY_ID,
        "param_version": ANTIEK_PARAM_VERSION,
        "schema_version": 40,
        "emitted_at": "2026-08-30T00:00:00Z",
        "document_id": None,
    }
    encoded = json.dumps(legacy_event, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()

    with connect_write(db_path, purpose="test/v40-resolution-seed") as con:
        FeedbackStore().resolve_thread(con, owner_user_id="owner-1", thread_id="fth-1")
        con.execute(
            "INSERT INTO write_event_outbox "
            "(event_id, operation_id, investigation_id, aggregate_kind, aggregate_id, "
            "event_json, event_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                legacy_event["event_id"],
                operation_id,
                legacy_event["investigation_id"],
                "feedback_thread",
                "fth-1",
                encoded,
                digest,
            ],
        )

    replay = resolve_feedback_thread(
        db_path,
        ResolveThreadCommand(
            owner_user_id="owner-1",
            thread_id="fth-1",
            idempotency_key="resolve-key-v40-replay",
        ),
    )
    assert replay.state == "resolved"

    with connect_write(db_path, purpose="test/v40-resolution-verify") as con:
        stored = event_for_operation(con, operation_id)
        rows = con.execute(
            "SELECT event_json FROM write_event_outbox WHERE operation_id=?", [operation_id]
        ).fetchall()
    assert stored is not None and stored.schema_version == 40
    assert isinstance(stored.payload, FeedbackThreadResolvedPayloadV40)
    assert stored.payload.resolution_event_id is None
    assert rows == [(encoded,)]
