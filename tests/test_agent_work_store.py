from __future__ import annotations

from datetime import UTC, datetime

from runtime.db_lock import connect_write
from substrate.agent_work.store import AgentWorkStore
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
