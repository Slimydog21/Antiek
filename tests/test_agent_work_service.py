from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.agent_work.service import CompleteReplyCommand, complete_agent_reply
from substrate.agent_work.store import AgentWorkStore
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand, FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.write.event_outbox import event_for_operation


def _seed(db_path: str) -> None:
    create_feedback_thread(
        db_path,
        CreateThreadCommand(
            thread_id="fth-1",
            root_item_id="fit-1",
            work_id="wrk-1",
            owner_user_id="owner-1",
            investigation_id="inv-1",
            logical_worker_id="research-owner",
            artifact=ArtifactVersionRef("artifact-1", 2, "a" * 64, "b" * 64),
            anchor=NodeTextAnchor("insight-1", "c" * 64, 0, 4, "fact", "", " remains"),
            body_markdown="Please verify this.",
            operation_id="feedback:create:op-1",
            request_sha256="d" * 64,
            context_sha256="e" * 64,
        ),
    )


def test_reply_callback_is_atomic_audited_and_exactly_replayable(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    with connect_write(db_path, purpose="test/lease-before-result") as con:
        lease = AgentWorkStore().lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            now=now,
            lease_seconds=120,
        )
        assert lease is not None

    command = CompleteReplyCommand(
        work_id="wrk-1",
        lease_id="lse-1",
        attempt_no=1,
        logical_worker_id="research-owner",
        bridge_credential_id="credential-1",
        reply_item_id="fit-2",
        reply_markdown="Verified against the primary paper.",
        agent_id="research-owner",
        idempotency_key="result-key-1",
        now=now,
    )
    first = complete_agent_reply(db_path, command)
    replay = complete_agent_reply(db_path, command)

    assert replay == first
    assert first.state == "replied"
    assert len(first.thread.items) == 2
    with connect_write(db_path, purpose="test/result-event") as con:
        event = event_for_operation(con, "agent-result:wrk-1:1")
    assert event is not None
    assert event.action_type == "artifact.feedback.replied"
    assert event.payload.reply_item_id == "fit-2"


def test_result_key_cannot_be_reused_with_different_reply(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    with connect_write(db_path, purpose="test/lease-before-conflict") as con:
        lease = AgentWorkStore().lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            now=now,
            lease_seconds=120,
        )
        assert lease is not None
    command = CompleteReplyCommand(
        work_id="wrk-1",
        lease_id="lse-1",
        attempt_no=1,
        logical_worker_id="research-owner",
        bridge_credential_id="credential-1",
        reply_item_id="fit-2",
        reply_markdown="First result.",
        agent_id="research-owner",
        idempotency_key="result-key-1",
        now=now,
    )
    complete_agent_reply(db_path, command)

    with pytest.raises(ValueError, match="different bytes"):
        complete_agent_reply(
            db_path,
            replace(command, reply_markdown="Conflicting result."),
        )


def test_reply_and_audit_event_roll_back_together(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    with connect_write(db_path, purpose="test/lease-before-rollback") as con:
        lease = AgentWorkStore().lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            now=now,
            lease_seconds=120,
        )
        assert lease is not None

    def fail_after_reply(boundary: str) -> None:
        if boundary == "after_reply":
            raise RuntimeError("callback boundary failure")

    with pytest.raises(RuntimeError, match="callback boundary failure"):
        complete_agent_reply(
            db_path,
            CompleteReplyCommand(
                work_id="wrk-1",
                lease_id="lse-1",
                attempt_no=1,
                logical_worker_id="research-owner",
                bridge_credential_id="credential-1",
                reply_item_id="fit-2",
                reply_markdown="This must roll back.",
                agent_id="research-owner",
                idempotency_key="result-key-1",
                now=now,
            ),
            checkpoint=fail_after_reply,
        )

    with connect_write(db_path, purpose="test/result-rollback-read") as con:
        thread = FeedbackStore().get_thread(con, owner_user_id="owner-1", thread_id="fth-1")
        assert thread is not None
        assert len(thread.items) == 1
        assert thread.work.state == "leased"
        assert event_for_operation(con, "agent-result:wrk-1:1") is None
