"""Connection-taking persistence for the diligence queue (autonomous-
diligence SPR-01).

Row CRUD under LockedConnection, following the substrate/books/highlights
conventions: frozen dataclasses, every write through one method, the
idempotent schema ensured on write entry points, read paths share the store
through the SqlExecutor protocol.

IDEMPOTENT FLAG CREATION on (owner, kind, object_ref): re-clicking a flag
affordance is a normal operator gesture, so a duplicate flag is never
written — an existing active row (queued/spawned/done) is returned as-is,
and re-flagging a DISMISSED row revives it to queued (the operator changed
their mind; the gesture stays safe and the queue keeps one row per object).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.diligence.schema import (
    FLAG_KINDS,
    FLAG_STATUSES,
    SqlExecutor,
    diligence_table_exists,
    init_diligence_schema,
)

_WS_RUN = re.compile(r"\s+")


def normalize_concept_key(raw: str) -> str:
    """The normalized concept key: whitespace collapsed, trimmed, lowercased
    — so "  Dark Matter  " and "dark matter" are ONE flag (idempotency works
    across the operator's casing/spacing variants)."""
    return _WS_RUN.sub(" ", raw).strip().lower()


@dataclass(frozen=True, slots=True)
class DiligenceFlagRow:
    """One queued flag (refs only — never the flagged object's text)."""

    flag_id: str
    owner_user_id: str
    kind: str
    object_ref: str
    note: str | None
    source_investigation_id: str | None
    source_document_id: str | None
    status: str
    spawned_investigation_id: str | None
    """The daemon's bookkeeping (SPR-03): WHY the row is where it is — the
    spawn iteration's receipt (reserve + caps checked) or the honest skip
    reason. JSON text; None until the daemon writes one."""
    receipt_json: str | None
    created_at: str
    updated_at: str


def _to_row(r: Any) -> DiligenceFlagRow:
    return DiligenceFlagRow(
        flag_id=str(r[0]),
        owner_user_id=str(r[1]),
        kind=str(r[2]),
        object_ref=str(r[3]),
        note=None if r[4] is None else str(r[4]),
        source_investigation_id=None if r[5] is None else str(r[5]),
        source_document_id=None if r[6] is None else str(r[6]),
        status=str(r[7]),
        spawned_investigation_id=None if r[8] is None else str(r[8]),
        receipt_json=None if r[9] is None else str(r[9]),
        created_at=str(r[10]),
        updated_at=str(r[11]),
    )


_SELECT = (
    "SELECT flag_id, owner_user_id, kind, object_ref, note, "
    "source_investigation_id, source_document_id, status, "
    "spawned_investigation_id, receipt_json, created_at, updated_at "
    "FROM diligence_queue"
)


@dataclass(frozen=True, slots=True)
class QueuedClaim:
    """One queued flag with its spawn question RESOLVED substrate-side:
    a concept flag's question is its normalized key; a node flag's is the
    node's canonical label (None when the node has vanished — the daemon
    skips it with an honest receipt, never a fabricated question). The
    daemon is substrate-internal, so claims span owners; the OWNER BOUNDARY
    is an API concern, and the flag's owner stays on the row for the
    write-back."""

    flag: DiligenceFlagRow
    question: str | None


def _to_claim(r: Any) -> QueuedClaim:
    return QueuedClaim(flag=_to_row(r), question=None if r[12] is None else str(r[12]))


def _mint_flag_id() -> str:
    return f"dfl-{secrets.token_hex(8)}"


class DiligenceStore:
    """Persist and read diligence flags, owner-scoped throughout."""

    def create_flag(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        kind: str,
        object_ref: str,
        note: str | None,
        source_investigation_id: str | None,
        source_document_id: str | None,
    ) -> tuple[DiligenceFlagRow, bool]:
        """Insert the flag, or return the EXISTING row for the same
        (owner, kind, object_ref) — idempotent by construction. Returns
        (row, created). A dismissed row is REVIVED to queued (with the new
        note when one is given); an active row is returned untouched.

        The concept key's canonical form is the STORE's job (boundary
        discipline): a concept ref normalizes HERE, so every writer — the
        API, a test, a future importer — converges on one row."""
        if kind not in FLAG_KINDS:
            raise ValueError(f"unknown diligence flag kind: {kind}")
        if kind == "concept":
            object_ref = normalize_concept_key(object_ref)
        init_diligence_schema(con)
        existing = self._find(con, owner_user_id=owner_user_id, kind=kind, object_ref=object_ref)
        if existing is not None:
            if existing.status != "dismissed":
                return existing, False
            con.execute(
                "UPDATE diligence_queue SET status = 'queued', "
                "note = COALESCE(?, note), updated_at = CURRENT_TIMESTAMP "
                "WHERE flag_id = ?",
                [note, existing.flag_id],
            )
            row = self.get_for_owner(
                con, owner_user_id=owner_user_id, flag_id=existing.flag_id
            )
            if row is None:  # survives `python -O`
                raise RuntimeError(
                    f"diligence flag {existing.flag_id} vanished after its revive"
                )
            return row, False
        flag_id = _mint_flag_id()
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, "
            "object_ref, note, source_investigation_id, source_document_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                flag_id,
                owner_user_id,
                kind,
                object_ref,
                note,
                source_investigation_id,
                source_document_id,
            ],
        )
        row = self.get_for_owner(con, owner_user_id=owner_user_id, flag_id=flag_id)
        if row is None:  # survives `python -O`
            raise RuntimeError(f"diligence flag {flag_id} vanished after its insert")
        return row, True

    def _find(
        self, con: SqlExecutor, *, owner_user_id: str, kind: str, object_ref: str
    ) -> DiligenceFlagRow | None:
        row = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND kind = ? AND object_ref = ? LIMIT 1",
            [owner_user_id, kind, object_ref],
        ).fetchone()
        return None if row is None else _to_row(row)

    def get_for_owner(
        self, con: SqlExecutor, *, owner_user_id: str, flag_id: str
    ) -> DiligenceFlagRow | None:
        """One flag, owner-scoped (another owner's id is a None, never a row)."""
        if not diligence_table_exists(con):
            return None
        row = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND flag_id = ? LIMIT 1",
            [owner_user_id, flag_id],
        ).fetchone()
        return None if row is None else _to_row(row)

    def list_for_owner(self, con: SqlExecutor, *, owner_user_id: str) -> list[DiligenceFlagRow]:
        """The owner's queue, NEWEST FIRST. Read-safe: no rows before the
        table exists."""
        if not diligence_table_exists(con):
            return []
        rows = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? "
            "ORDER BY created_at DESC, flag_id DESC",
            [owner_user_id],
        ).fetchall()
        return [_to_row(r) for r in rows]

    def list_queued_claims(self, con: SqlExecutor) -> list[QueuedClaim]:
        """The daemon's claim query (autonomous-diligence SPR-02): every
        queued flag, OLDEST FIRST, with the spawn question resolved
        substrate-side (concept key, or the node's canonical label via a
        LEFT JOIN — a vanished node yields a NULL question and the daemon
        skips it honestly). Already-spawned/dismissed flags are excluded by
        the status filter — the first dedupe path is the query itself."""
        if not diligence_table_exists(con):
            return []
        rows = con.execute(
            "SELECT q.flag_id, q.owner_user_id, q.kind, q.object_ref, q.note, "
            "q.source_investigation_id, q.source_document_id, q.status, "
            "q.spawned_investigation_id, q.receipt_json, q.created_at, q.updated_at, "
            "CASE WHEN q.kind = 'concept' THEN q.object_ref "
            "ELSE n.canonical_label END "
            "FROM diligence_queue q "
            "LEFT JOIN nodes n ON n.node_id = q.object_ref AND n.node_type = "
            "CASE q.kind WHEN 'open_question' THEN 'question' "
            "WHEN 'insight' THEN 'insight' END "
            "WHERE q.status = 'queued' "
            "ORDER BY q.created_at ASC, q.flag_id ASC",
        ).fetchall()
        return [_to_claim(r) for r in rows]

    def dismiss(
        self, con: LockedConnection, *, owner_user_id: str, flag_id: str
    ) -> DiligenceFlagRow | None:
        """queued → dismissed. Returns the row; None when the flag isn't the
        owner's. An already-dismissed row is returned unchanged (idempotent);
        a spawned/done row is NOT dismissable here — the route answers 409
        from the returned row's status (this method changes nothing then)."""
        init_diligence_schema(con)
        row = self.get_for_owner(con, owner_user_id=owner_user_id, flag_id=flag_id)
        if row is None or row.status != "queued":
            return row
        con.execute(
            "UPDATE diligence_queue SET status = 'dismissed', "
            "updated_at = CURRENT_TIMESTAMP WHERE flag_id = ?",
            [flag_id],
        )
        out = self.get_for_owner(con, owner_user_id=owner_user_id, flag_id=flag_id)
        assert out is not None  # the update above just landed
        return out

    def mark_spawned(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        flag_id: str,
        spawned_investigation_id: str,
        receipt_json: str | None = None,
    ) -> DiligenceFlagRow | None:
        """queued → spawned with the spawned investigation id AND the spawn
        iteration's receipt (SPR-03: which caps were checked, the reserve
        amount) in ONE statement — the write-back is a single bounded
        scope. The SPR-02 daemon write path (claimed flags only)."""
        init_diligence_schema(con)
        row = self.get_for_owner(con, owner_user_id=owner_user_id, flag_id=flag_id)
        if row is None or row.status != "queued":
            return row
        con.execute(
            "UPDATE diligence_queue SET status = 'spawned', "
            "spawned_investigation_id = ?, receipt_json = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE flag_id = ?",
            [spawned_investigation_id, receipt_json, flag_id],
        )
        out = self.get_for_owner(con, owner_user_id=owner_user_id, flag_id=flag_id)
        assert out is not None  # the update above just landed
        return out

    def record_skip(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        flag_id: str,
        receipt_json: str,
    ) -> None:
        """Record the honest skip reason on a QUEUED flag (SPR-03's daemon
        bookkeeping — a cap hit, a dedupe, a concurrency wait). Status stays
        queued; the receipt is rewritten next iteration while the cause
        persists. No-op for rows that left queued between claim and write."""
        init_diligence_schema(con)
        con.execute(
            "UPDATE diligence_queue SET receipt_json = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE flag_id = ? AND owner_user_id = ? AND status = 'queued'",
            [receipt_json, flag_id, owner_user_id],
        )


# ── The lazy terminal projection (SPR-03) ─────────────────────────────

#: The terminal set the monitor already trusts (cascade_session.py:426-430),
#: mapped to the flag's honest OUTCOME vocabulary: a budget-halted spawn
#: reads stopped (app.py:3026-3033's terminal-honest rule), never "running".
SPAWNED_TERMINAL_OUTCOMES: dict[str, str] = {
    "investigation.completed": "completed",
    "investigation.failed": "failed",
    "investigation.chase_halted": "stopped",
}


def project_flag_status(
    row: DiligenceFlagRow, spawned_terminal_action: str | None
) -> tuple[str, str | None]:
    """The lazy, read-only projection: a SPAWNED flag whose investigation
    reached a terminal event reads done with the honest outcome; everything
    else reads as stored. The caller supplies the terminal action from the
    event log (None = still in flight) — the projection itself is pure.

    Returns (status, outcome): ("done", "completed" | "failed" | "stopped")
    for a terminal spawned flag, else (row.status, None)."""
    if row.status == "spawned" and spawned_terminal_action is not None:
        outcome = SPAWNED_TERMINAL_OUTCOMES.get(spawned_terminal_action)
        if outcome is not None:
            return "done", outcome
    return row.status, None


# Re-export so consumers read the vocabulary from one place.
__all__ = [
    "DiligenceFlagRow",
    "DiligenceStore",
    "FLAG_KINDS",
    "FLAG_STATUSES",
    "QueuedClaim",
    "SPAWNED_TERMINAL_OUTCOMES",
    "normalize_concept_key",
    "project_flag_status",
]
