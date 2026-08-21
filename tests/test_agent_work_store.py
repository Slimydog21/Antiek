from __future__ import annotations

from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.agent_work.store import AgentWorkStore, LeaseConflict
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand
from substrate.graph.schema import init_database_at_path


def _command() -> CreateThreadCommand:
    return CreateThreadCommand(
        thread_id="fth-1",
        root_item_id="fit-1",
        work_id="wrk-1",
        owner_user_id="owner-1",
        investigation_id="inv-1",
        logical_worker_id="research-owner",
        artifact=ArtifactVersionRef("artifact-1", 2, "a" * 64, "b" * 64),
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


def test_worker_leases_one_queued_comment_with_canonical_context(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    create_feedback_thread(db_path, _command())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

    with connect_write(db_path, purpose="test/agent-work-lease") as con:
        lease = AgentWorkStore().lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            now=now,
            lease_seconds=120,
        )
        second = AgentWorkStore().lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-2",
            lease_id="lse-2",
            now=now,
            lease_seconds=120,
        )

    assert lease is not None
    assert lease.work_id == "wrk-1"
    assert lease.thread_id == "fth-1"
    assert lease.lease_id == "lse-1"
    assert lease.attempt_no == 1
    assert lease.artifact.version == 2
    assert lease.comment_markdown == "Please verify this against the primary paper."
    assert lease.logical_worker_id == "research-owner"
    assert second is None


def test_only_the_live_lease_can_mark_work_submitted(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    create_feedback_thread(db_path, _command())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

    with connect_write(db_path, purpose="test/agent-work-submit") as con:
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
        submitted = AgentWorkStore().mark_submitted(
            con,
            work_id=lease.work_id,
            lease_id=lease.lease_id,
            attempt_no=lease.attempt_no,
            logical_worker_id="research-owner",
            now=now,
            adapter_version="herdr-bridge/0.1",
            herdr_target_observed="agent-7",
        )
        with pytest.raises(LeaseConflict):
            AgentWorkStore().mark_submitted(
                con,
                work_id=lease.work_id,
                lease_id="lse-wrong",
                attempt_no=lease.attempt_no,
                logical_worker_id="research-owner",
                now=now,
                adapter_version="herdr-bridge/0.1",
                herdr_target_observed="agent-7",
            )

    assert submitted.state == "submitted"
    assert submitted.attempt_no == 1


def test_live_lease_appends_one_agent_reply_and_completes_work(tmp_path) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    create_feedback_thread(db_path, _command())
    now = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

    with connect_write(db_path, purpose="test/agent-work-reply") as con:
        store = AgentWorkStore()
        lease = store.lease_one(
            con,
            logical_worker_id="research-owner",
            bridge_credential_id="credential-1",
            bridge_instance_id="mini-1",
            lease_id="lse-1",
            now=now,
            lease_seconds=120,
        )
        assert lease is not None
        store.mark_submitted(
            con,
            work_id=lease.work_id,
            lease_id=lease.lease_id,
            attempt_no=lease.attempt_no,
            logical_worker_id="research-owner",
            now=now,
            adapter_version="herdr-bridge/0.1",
            herdr_target_observed="agent-7",
        )
        completed = store.complete_with_reply(
            con,
            work_id=lease.work_id,
            lease_id=lease.lease_id,
            attempt_no=lease.attempt_no,
            logical_worker_id="research-owner",
            result_sha256="f" * 64,
            reply_item_id="fit-2",
            reply_markdown="I checked the primary paper and added the missing evidence.",
            agent_id="research-owner",
            now=now,
        )

    assert completed.state == "replied"
    assert completed.reply_item_id == "fit-2"
    assert [item.body_markdown for item in completed.thread.items] == [
        "Please verify this against the primary paper.",
        "I checked the primary paper and added the missing evidence.",
    ]
