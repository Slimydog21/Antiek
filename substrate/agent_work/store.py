"""Single-writer persistence for leasing canonical agent work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from runtime.db_lock import LockedConnection
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.schema import init_feedback_schema


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
