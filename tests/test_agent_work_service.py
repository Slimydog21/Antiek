from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from runtime.db_lock import connect_write
from substrate.agent_work.service import (
    CompleteDispositionCommand,
    CompleteFailureCommand,
    CompleteReplyCommand,
    LeaseWorkCommand,
    MarkAcknowledgedCommand,
    MarkSubmittedCommand,
    MarkWorkingCommand,
    RenewLeaseCommand,
    complete_agent_disposition,
    complete_agent_failure,
    complete_agent_reply,
    lease_agent_work,
    mark_agent_work_acknowledged,
    mark_agent_work_submitted,
    mark_agent_work_working,
    renew_agent_work_lease,
)
from substrate.agent_work.store import AgentWorkStore
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand, FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.write.event_outbox import event_for_operation

TEST_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


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
    with connect_write(db_path, purpose="test/seed-agent-work-clock") as con:
        con.execute(
            "UPDATE agent_work SET not_before=? WHERE work_id='wrk-1'",
            [TEST_NOW],
        )


def test_reply_callback_is_atomic_audited_and_exactly_replayable(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
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
        context_sha256="e" * 64,
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
        transitioned = event_for_operation(con, "agent-transition:wrk-1:1:replied")
    assert event is not None
    assert event.action_type == "artifact.feedback.replied"
    assert event.payload.reply_item_id == "fit-2"
    assert transitioned is not None
    assert transitioned.payload.before_state == "leased"
    assert transitioned.payload.after_state == "replied"


def test_lease_command_is_atomic_audited_and_exactly_replayable(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    command = LeaseWorkCommand(
        logical_worker_id="research-owner",
        bridge_credential_id="credential-1",
        bridge_instance_id="mini-1",
        lease_id="lse-1",
        lease_seconds=120,
        idempotency_key="lease-key-1",
        now=TEST_NOW + timedelta(minutes=1),
    )

    first = lease_agent_work(db_path, command)
    replay = lease_agent_work(db_path, command)

    assert replay == first
    assert first is not None
    assert first.work_id == "wrk-1"
    with connect_write(db_path, purpose="test/lease-event") as con:
        transitioned = event_for_operation(con, "agent-transition:wrk-1:1:leased")
    assert transitioned is not None
    assert transitioned.payload.before_state == "queued"
    assert transitioned.payload.after_state == "leased"


def test_expired_lease_is_audited_requeued_and_released_as_next_attempt(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
    first = lease_agent_work(
        db_path,
        LeaseWorkCommand(
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            lease_seconds=30,
            idempotency_key="lease-key-1",
            now=now,
        ),
    )
    assert first is not None

    second = lease_agent_work(
        db_path,
        LeaseWorkCommand(
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-2",
            lease_id="lse-2",
            lease_seconds=120,
            idempotency_key="lease-key-2",
            now=now + timedelta(seconds=31),
        ),
    )

    assert second is not None
    assert second.work_id == first.work_id
    assert second.attempt_no == 2
    assert second.lease_id == "lse-2"
    with connect_write(db_path, purpose="test/expired-lease-event") as con:
        expired = event_for_operation(con, "agent-transition:wrk-1:1:lease_expired")
    assert expired is not None
    assert expired.payload.before_state == "leased"
    assert expired.payload.after_state == "queued"


def test_submitted_command_is_atomic_audited_and_exactly_replayable(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
    lease = lease_agent_work(
        db_path,
        LeaseWorkCommand(
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            lease_seconds=120,
            idempotency_key="lease-key-1",
            now=now,
        ),
    )
    assert lease is not None
    command = MarkSubmittedCommand(
        work_id=lease.work_id,
        lease_id=lease.lease_id,
        attempt_no=lease.attempt_no,
        logical_worker_id="research-owner",
        bridge_credential_id="credential-1",
        adapter_version="herdr-bridge/0.1",
        herdr_target_observed="agent-7",
        idempotency_key="submitted-key-1",
        now=now,
    )

    first = mark_agent_work_submitted(db_path, command)
    replay = mark_agent_work_submitted(db_path, command)

    assert replay == first
    assert first.state == "submitted"
    with connect_write(db_path, purpose="test/submitted-event") as con:
        transitioned = event_for_operation(con, "agent-transition:wrk-1:1:submitted")
    assert transitioned is not None
    assert transitioned.payload.before_state == "leased"
    assert transitioned.payload.after_state == "submitted"


def test_result_key_cannot_be_reused_with_different_reply(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
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
        context_sha256="e" * 64,
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


def test_conflicting_result_key_is_serialized_under_concurrency(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
    lease = lease_agent_work(
        db_path,
        LeaseWorkCommand(
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            lease_seconds=120,
            idempotency_key="lease-key-1",
            now=now,
        ),
    )
    assert lease is not None
    command = CompleteReplyCommand(
        work_id=lease.work_id,
        lease_id=lease.lease_id,
        attempt_no=lease.attempt_no,
        logical_worker_id="research-owner",
        bridge_credential_id="credential-1",
        context_sha256=lease.context_sha256,
        reply_item_id="fit-2",
        reply_markdown="First contender.",
        agent_id="research-owner",
        idempotency_key="result-key-1",
        now=now,
    )

    def complete(body: str):
        return complete_agent_reply(db_path, replace(command, reply_markdown=body))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(complete, "First contender."),
            pool.submit(complete, "Second contender."),
        ]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(("ok", future.result().thread.items[-1].body_markdown))
        except ValueError as exc:
            outcomes.append(("conflict", str(exc)))

    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"]
    assert "different bytes" in next(value for kind, value in outcomes if kind == "conflict")


def test_decline_audit_preserves_disposition_semantics(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
    lease = lease_agent_work(
        db_path,
        LeaseWorkCommand(
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            lease_seconds=120,
            idempotency_key="lease-key-1",
            now=now,
        ),
    )
    assert lease is not None

    result = complete_agent_disposition(
        db_path,
        CompleteDispositionCommand(
            work_id=lease.work_id,
            lease_id=lease.lease_id,
            attempt_no=lease.attempt_no,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            context_sha256=lease.context_sha256,
            kind="decline",
            message_item_id="fit-2",
            message_markdown="This request needs a source I cannot access.",
            agent_id="research-owner",
            idempotency_key="disposition-key-1",
            now=now,
        ),
    )

    assert result.state == "declined"
    with connect_write(db_path, purpose="test/disposition-event") as con:
        event = event_for_operation(con, "agent-result:wrk-1:1")
    assert event is not None
    assert event.payload.result_kind == "decline"


def test_reply_and_audit_event_roll_back_together(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
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
                context_sha256="e" * 64,
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


ROLLBACK_CASES = [
    ("lease", boundary)
    for boundary in ("after_lease_store", "after_lease_event", "after_lease_receipt")
] + [
    ("renew", boundary)
    for boundary in ("after_renew_store", "after_renew_receipt")
] + [
    ("submitted", boundary)
    for boundary in (
        "after_submitted_store",
        "after_submitted_event",
        "after_submitted_receipt",
    )
] + [
    ("acknowledged", boundary)
    for boundary in (
        "after_acknowledged_store",
        "after_acknowledged_event",
        "after_acknowledged_receipt",
    )
] + [
    ("working", boundary)
    for boundary in (
        "after_working_store",
        "after_working_event",
        "after_working_receipt",
    )
] + [
    ("failure", boundary)
    for boundary in (
        "after_failure_store",
        "after_failure_event",
        "after_failure_receipt",
    )
] + [
    ("reply", boundary)
    for boundary in (
        "after_reply",
        "after_reply_feedback_event",
        "after_reply_transition_event",
        "after_receipt",
    )
] + [
    ("disposition", boundary)
    for boundary in (
        "after_disposition_store",
        "after_disposition_feedback_event",
        "after_disposition_transition_event",
        "after_disposition_receipt",
    )
]


def _transaction_snapshot(db_path: str) -> tuple[object, ...]:
    with connect_write(db_path, purpose="test/transaction-snapshot") as con:
        work = con.execute(
            "SELECT state, attempt_count, active_lease_id, lease_expires_at, "
            "last_error_code, result_sha256, terminal_at FROM agent_work "
            "WHERE work_id='wrk-1'"
        ).fetchone()
        attempts = con.execute(
            "SELECT attempt_no, state, lease_expires_at, submitted_at, "
            "acknowledged_at, working_at, completed_at FROM agent_work_attempts "
            "ORDER BY attempt_no"
        ).fetchall()
        counts = (
            con.execute("SELECT count(*) FROM feedback_items").fetchone()[0],
            con.execute("SELECT count(*) FROM write_event_outbox").fetchone()[0],
            con.execute("SELECT count(*) FROM feedback_command_receipts").fetchone()[0],
        )
    return work, tuple(attempts), counts


@pytest.mark.parametrize(("operation", "boundary"), ROLLBACK_CASES)
def test_bridge_commands_roll_back_at_every_service_boundary(
    tmp_path, operation: str, boundary: str
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    _seed(db_path)
    now = TEST_NOW + timedelta(minutes=1)
    lease = None
    if operation != "lease":
        lease = lease_agent_work(
            db_path,
            LeaseWorkCommand(
                logical_worker_id="research-owner",
                bridge_credential_id="credential-1",
                bridge_instance_id="mini-1",
                lease_id="lse-setup",
                lease_seconds=120,
                idempotency_key="lease-setup-key",
                now=now,
            ),
        )
        assert lease is not None
    if operation in {"acknowledged", "working"}:
        mark_agent_work_submitted(
            db_path,
            MarkSubmittedCommand(
                work_id="wrk-1",
                lease_id="lse-setup",
                attempt_no=1,
                logical_worker_id="research-owner",
                bridge_credential_id="credential-1",
                adapter_version="herdr-bridge/0.1",
                herdr_target_observed="agent-7",
                idempotency_key="submitted-setup-key",
                now=now,
            ),
        )
    before = _transaction_snapshot(db_path)

    def fail(selected: str) -> None:
        if selected == boundary:
            raise RuntimeError("injected boundary failure")

    common = {
        "work_id": "wrk-1",
        "lease_id": "lse-setup",
        "attempt_no": 1,
        "logical_worker_id": "research-owner",
        "bridge_credential_id": "credential-1",
        "idempotency_key": f"{operation}-test-key",
        "now": now,
    }
    with pytest.raises(RuntimeError, match="injected boundary failure"):
        if operation == "lease":
            lease_agent_work(
                db_path,
                LeaseWorkCommand(
                    logical_worker_id="research-owner",
                    bridge_credential_id="credential-1",
                    bridge_instance_id="mini-1",
                    lease_id="lse-test",
                    lease_seconds=120,
                    idempotency_key="lease-test-key",
                    now=now,
                ),
                checkpoint=fail,
            )
        elif operation == "renew":
            renew_agent_work_lease(
                db_path,
                RenewLeaseCommand(**common, lease_seconds=240),
                checkpoint=fail,
            )
        elif operation == "submitted":
            mark_agent_work_submitted(
                db_path,
                MarkSubmittedCommand(
                    **common,
                    adapter_version="herdr-bridge/0.1",
                    herdr_target_observed="agent-7",
                ),
                checkpoint=fail,
            )
        elif operation == "acknowledged":
            mark_agent_work_acknowledged(
                db_path,
                MarkAcknowledgedCommand(
                    **common,
                    transport_receipt_sha256="f" * 64,
                ),
                checkpoint=fail,
            )
        elif operation == "working":
            mark_agent_work_working(
                db_path,
                MarkWorkingCommand(**common),
                checkpoint=fail,
            )
        elif operation == "failure":
            complete_agent_failure(
                db_path,
                CompleteFailureCommand(
                    **common,
                    context_sha256="e" * 64,
                    error_code="herdr_unavailable",
                    retryable=True,
                ),
                checkpoint=fail,
            )
        elif operation == "reply":
            complete_agent_reply(
                db_path,
                CompleteReplyCommand(
                    **common,
                    context_sha256="e" * 64,
                    reply_item_id="fit-rollback",
                    reply_markdown="This response must roll back.",
                    agent_id="research-owner",
                ),
                checkpoint=fail,
            )
        else:
            complete_agent_disposition(
                db_path,
                CompleteDispositionCommand(
                    **common,
                    context_sha256="e" * 64,
                    kind="decline",
                    message_item_id="fit-rollback",
                    message_markdown="Cannot complete this request.",
                    agent_id="research-owner",
                ),
                checkpoint=fail,
            )

    assert _transaction_snapshot(db_path) == before
