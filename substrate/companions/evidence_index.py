"""The evidence index — the agent-facing evidence base (companions SPR-01).

A REBUILDABLE CACHE with a stable-id contract, NEVER a truth: every row is
projected from stores their readers already own (graph nodes, the event
log, unit-1 anchors, unit-7 diligence flags, unit-4 reading state), so the
table can be dropped and rebuilt from scratch with IDENTICAL ids — the
parity contract is a test, not a promise.

The id contract: ``evidence_id`` is content-derived —
sha256(kind · claim identity · sorted refs) — stable across rebuilds BY
CONSTRUCTION. THE COLLISION CONTRACT (explicit): two projection inputs that
share kind + identity + refs ARE the same evidence and dedupe onto one row;
a collision between genuinely different sources is a sha256 collision, and
the rebuild REFUSES to write two live rows with one id (it raises — never
a silent overwrite, never a re-point).

REFS ONLY: refs_json carries node ids, investigation ids, anchor refs,
artifact path hashes — never the object's text (the claim's text feeds the
id's hash at projection time and is discarded; it is never stored).

TOMBSTONE honesty: a source that vanishes between rebuilds leaves its row
TOMBstoned (same id, tombstone=true) — agents holding the id resolve an
honest tombstone, never a dangling reference, never a silent re-point. A
from-scratch rebuild carries no tombstones (nothing to remember) — the
parity contract covers live ids.

Bounded writes (the arXiv lesson, tools/arxiv_oai_sync.py:44-47,105-107):
``rebuild_scope`` writes in bounded batches, never one long lock hold.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the unit-1
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


#: The scope vocabulary. PROJECT scope keys on the unit-3 workstation id
#: when the container lands; before that, project-scope rebuild is honestly
#: UNAVAILABLE (the projector raises, never mints a synthetic project id).
SCOPES = ("project", "document")

#: The row kinds: a claim (insight/question node), its evidence (anchor /
#: grounding ref), and the process that produced it (thread, diligence run,
#: reading position).
KINDS = ("claim", "evidence", "process")

DDL = """
CREATE TABLE IF NOT EXISTS evidence_index (
  evidence_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  scope VARCHAR NOT NULL CHECK (scope IN ('project', 'document')),
  scope_id VARCHAR NOT NULL,
  kind VARCHAR NOT NULL CHECK (kind IN ('claim', 'evidence', 'process')),
  refs_json VARCHAR NOT NULL,
  tombstone BOOLEAN NOT NULL DEFAULT FALSE,
  rebuilt_at VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_index_scope
  ON evidence_index(owner_user_id, scope, scope_id, kind);
"""

#: SPR-03 (event wiring): the rebuild receipts + the watcher's dedupe state.
#: Receipts make "rebuilt at T because of events E" DATA, not copy; the
#: seen-trigger table is the duplicate-delivery dedupe (one event id ⇒ at
#: most one trigger); the watcher-state table carries the diligence
#: watermark (unit-7's transitions are DB rows on this stack — the trigger
#: reads the status watermark, honestly).
WIRING_DDL = """
CREATE TABLE IF NOT EXISTS companion_rebuild_receipts (
  rebuild_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  scope VARCHAR NOT NULL CHECK (scope IN ('project', 'document')),
  scope_id VARCHAR NOT NULL,
  trigger_event_ids_json VARCHAR NOT NULL,
  rows_written INTEGER NOT NULL CHECK (rows_written >= 0),
  duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
  status VARCHAR NOT NULL CHECK (status IN ('completed', 'failed')),
  error VARCHAR,
  rebuilt_at VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_companion_receipts_scope
  ON companion_rebuild_receipts(owner_user_id, scope, scope_id, rebuilt_at);

CREATE TABLE IF NOT EXISTS companion_seen_triggers (
  event_id VARCHAR PRIMARY KEY,
  seen_at VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS companion_seen_triggers_by_owner (
  event_id VARCHAR NOT NULL,
  owner_user_id VARCHAR NOT NULL,
  seen_at VARCHAR NOT NULL,
  PRIMARY KEY (event_id, owner_user_id)
);

CREATE TABLE IF NOT EXISTS companion_watcher_state (
  state_key VARCHAR PRIMARY KEY,
  state_value VARCHAR NOT NULL
);
"""

#: Rebuild write batch size — many short scopes, never one long one.
REBUILD_BATCH_SIZE = 100


def init_evidence_index_schema(con: LockedConnection) -> None:
    """Create the additive evidence-index schema on an existing writer
    connection (idempotent)."""
    con.execute(DDL)
    con.execute(WIRING_DDL)
    # The legacy seen-trigger table predates owner scoping and only ever
    # ran under the single-operator deployment, so its rows carry over
    # attributed to the default operator — never re-triggering, never lost.
    con.execute(
        "INSERT INTO companion_seen_triggers_by_owner "
        "SELECT event_id, '__operator__', seen_at "
        "FROM companion_seen_triggers ON CONFLICT DO NOTHING"
    )


def evidence_index_table_exists(con: object) -> bool:
    """Whether the table is present (read paths never run DDL)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'evidence_index' LIMIT 1"
    ).fetchone()
    return row is not None


def make_evidence_id(kind: str, identity: str, refs: list[str]) -> str:
    """The content-derived stable id: sha over kind + the claim identity +
    the SORTED refs. The identity is the claim's text for claim rows (read
    substrate-side at projection time, hashed, NEVER stored) or the ref
    identity for evidence/process rows."""
    material = "\x1f".join([kind, identity, *sorted(refs)])
    return "ev-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    """One index row — refs only, never content."""

    evidence_id: str
    owner_user_id: str
    scope: str
    scope_id: str
    kind: str
    refs: tuple[str, ...]
    tombstone: bool
    rebuilt_at: str


def _to_row(r: Any) -> EvidenceRow:
    refs = json.loads(str(r[5]))
    return EvidenceRow(
        evidence_id=str(r[0]),
        owner_user_id=str(r[1]),
        scope=str(r[2]),
        scope_id=str(r[3]),
        kind=str(r[4]),
        refs=tuple(sorted(str(x) for x in refs)),
        tombstone=bool(r[6]),
        rebuilt_at=str(r[7]),
    )


def rebuild_scope(
    con: LockedConnection,
    *,
    owner_user_id: str,
    scope: str,
    scope_id: str,
    rows: list[EvidenceRow],
    batch_size: int = REBUILD_BATCH_SIZE,
) -> None:
    """TOTAL idempotent rebuild of one scope: read the incumbent rows (for
    the tombstone carry), delete the scope, batch-insert the new rows plus
    the carried tombstones. Deterministic: identical sources ⇒ identical
    table, byte for byte.

    The collision contract is enforced HERE: two live rows sharing an id
    raise (a genuine collision is a substrate bug, never silently merged).
    """
    init_evidence_index_schema(con)
    seen: dict[str, EvidenceRow] = {}
    for row in rows:
        incumbent = seen.get(row.evidence_id)
        if incumbent is not None and incumbent != row:
            raise ValueError(
                f"evidence-id collision on {row.evidence_id}: two DIFFERENT "
                "rows claim one id (the collision contract refuses the write)"
            )
        seen[row.evidence_id] = row

    incumbent_rows = con.execute(
        "SELECT evidence_id, owner_user_id, scope, scope_id, kind, refs_json, "
        "tombstone, rebuilt_at FROM evidence_index "
        "WHERE owner_user_id = ? AND scope = ? AND scope_id = ?",
        [owner_user_id, scope, scope_id],
    ).fetchall()
    # The tombstone carry: a row whose source vanished since the last rebuild
    # persists TOMBstoned (same id) — never dangling, never re-pointed.
    carried: list[EvidenceRow] = []
    for raw in incumbent_rows:
        old = _to_row(raw)
        if old.evidence_id not in seen and not old.tombstone:
            rebuilt_at = rows[0].rebuilt_at if rows else old.rebuilt_at
            carried.append(
                EvidenceRow(
                    evidence_id=old.evidence_id,
                    owner_user_id=old.owner_user_id,
                    scope=old.scope,
                    scope_id=old.scope_id,
                    kind=old.kind,
                    refs=old.refs,
                    tombstone=True,
                    rebuilt_at=rebuilt_at,
                )
            )

    out = sorted([*seen.values(), *carried], key=lambda r: r.evidence_id)
    # ATOMICITY (SPR-03's last-good discipline): the DELETE + the batch
    # INSERTs land together or not at all — a failed rebuild NEVER leaves a
    # half-written scope (DuckDB autocommits per statement; the explicit
    # transaction is the only honest shape, runtime/db_lock.py:586).
    with con.transaction():
        con.execute(
            "DELETE FROM evidence_index WHERE owner_user_id = ? AND scope = ? AND scope_id = ?",
            [owner_user_id, scope, scope_id],
        )
        for i in range(0, len(out), batch_size):
            batch = out[i : i + batch_size]
            con.executemany(
                "INSERT INTO evidence_index (evidence_id, owner_user_id, scope, "
                "scope_id, kind, refs_json, tombstone, rebuilt_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        r.evidence_id,
                        r.owner_user_id,
                        r.scope,
                        r.scope_id,
                        r.kind,
                        json.dumps(sorted(r.refs)),
                        r.tombstone,
                        r.rebuilt_at,
                    )
                    for r in batch
                ],
            )


def read_scope(
    con: SqlExecutor, *, owner_user_id: str, scope: str, scope_id: str
) -> list[EvidenceRow]:
    """One scope's rows, sorted by evidence_id (deterministic render order).
    Read-safe: no rows before the table exists."""
    if not evidence_index_table_exists(con):
        return []
    rows = con.execute(
        "SELECT evidence_id, owner_user_id, scope, scope_id, kind, refs_json, "
        "tombstone, rebuilt_at FROM evidence_index "
        "WHERE owner_user_id = ? AND scope = ? AND scope_id = ? "
        "ORDER BY evidence_id ASC",
        [owner_user_id, scope, scope_id],
    ).fetchall()
    return [_to_row(r) for r in rows]


def resolve(con: SqlExecutor, evidence_id: str) -> EvidenceRow | None:
    """One id → its row (a tombstoned row INCLUDED — that IS the honest
    tombstone). None only when the id was never projected."""
    if not evidence_index_table_exists(con):
        return None
    row = con.execute(
        "SELECT evidence_id, owner_user_id, scope, scope_id, kind, refs_json, "
        "tombstone, rebuilt_at FROM evidence_index WHERE evidence_id = ? LIMIT 1",
        [evidence_id],
    ).fetchone()
    return None if row is None else _to_row(row)


def query_claim_node_ids(
    con: SqlExecutor, *, owner_user_id: str, source_document_id: str | None
) -> list[str]:
    """The flywheel hook's additive consumer query (companions SPR-01): the
    LIVE claim rows the index already holds for a source document → their
    node refs. An absent table or empty index returns [] — the hook's
    behavior is then byte-identical to today (the trajectory re-walk runs
    exactly as before)."""
    if source_document_id is None or not evidence_index_table_exists(con):
        return []
    rows = con.execute(
        "SELECT refs_json FROM evidence_index WHERE owner_user_id = ? "
        "AND scope = 'document' AND scope_id = ? AND kind = 'claim' "
        "AND tombstone = FALSE ORDER BY evidence_id ASC",
        [owner_user_id, source_document_id],
    ).fetchall()
    out: list[str] = []
    for (refs_json,) in rows:
        for ref in json.loads(str(refs_json)):
            if ref.startswith("node:"):
                out.append(ref[len("node:") :])
    return out


# ── SPR-03: rebuild receipts + the watcher's dedupe state ────────────────


@dataclass(frozen=True, slots=True)
class RebuildReceipt:
    """The rebuild's operator-visible honesty: WHICH events triggered it,
    HOW MANY rows landed, how long it took, and whether it failed (the
    last-good generation keeps serving on failure)."""

    rebuild_id: str
    owner_user_id: str
    scope: str
    scope_id: str
    trigger_event_ids: tuple[str, ...]
    rows_written: int
    duration_ms: int
    status: str  # completed | failed
    error: str | None
    rebuilt_at: str


def record_receipt(con: LockedConnection, receipt: RebuildReceipt) -> None:
    """Append the rebuild's receipt (one bounded write — the receipt is the
    rebuild's own audit, written in its own short scope)."""
    init_evidence_index_schema(con)
    con.execute(
        "INSERT INTO companion_rebuild_receipts (rebuild_id, owner_user_id, "
        "scope, scope_id, trigger_event_ids_json, rows_written, duration_ms, "
        "status, error, rebuilt_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            receipt.rebuild_id,
            receipt.owner_user_id,
            receipt.scope,
            receipt.scope_id,
            json.dumps(sorted(receipt.trigger_event_ids)),
            receipt.rows_written,
            receipt.duration_ms,
            receipt.status,
            receipt.error,
            receipt.rebuilt_at,
        ],
    )


def list_receipts(
    con: SqlExecutor, *, owner_user_id: str, scope: str, scope_id: str
) -> list[RebuildReceipt]:
    """A scope's receipts, newest first."""
    if not evidence_index_table_exists(con):
        return []
    rows = con.execute(
        "SELECT rebuild_id, owner_user_id, scope, scope_id, "
        "trigger_event_ids_json, rows_written, duration_ms, status, error, "
        "rebuilt_at FROM companion_rebuild_receipts "
        "WHERE owner_user_id = ? AND scope = ? AND scope_id = ? "
        "ORDER BY rebuilt_at DESC, rebuild_id DESC",
        [owner_user_id, scope, scope_id],
    ).fetchall()
    return [
        RebuildReceipt(
            rebuild_id=str(r[0]),
            owner_user_id=str(r[1]),
            scope=str(r[2]),
            scope_id=str(r[3]),
            trigger_event_ids=tuple(sorted(str(x) for x in json.loads(str(r[4])))),
            rows_written=int(r[5]),
            duration_ms=int(r[6]),
            status=str(r[7]),
            error=None if r[8] is None else str(r[8]),
            rebuilt_at=str(r[9]),
        )
        for r in rows
    ]


def seen_trigger_ids(con: SqlExecutor, *, owner_user_id: str) -> set[str]:
    """Every trigger event id THIS OWNER's watcher has consumed (the
    duplicate-delivery dedupe — one event id triggers at most one rebuild
    per owner; the rebuild itself is owner-scoped)."""
    if not evidence_index_table_exists(con):
        return set()
    rows = con.execute(
        "SELECT event_id FROM companion_seen_triggers_by_owner "
        "WHERE owner_user_id = ?",
        [owner_user_id],
    ).fetchall()
    return {str(r[0]) for r in rows}


def mark_triggers_seen(
    con: LockedConnection,
    owner_user_id: str,
    event_ids: list[str],
    seen_at: str,
) -> None:
    """Mark trigger ids consumed FOR THIS OWNER — batched, one short write
    scope. A second owner's watcher still sees (and rebuilds for) the same
    event; consumption is per-owner, never global."""
    if not event_ids:
        return
    init_evidence_index_schema(con)
    con.executemany(
        "INSERT INTO companion_seen_triggers_by_owner "
        "(event_id, owner_user_id, seen_at) VALUES (?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        [(eid, owner_user_id, seen_at) for eid in event_ids],
    )


def watcher_state_get(con: SqlExecutor, key: str) -> str | None:
    """A watcher-state value (the diligence status watermark), None when
    unset."""
    if not evidence_index_table_exists(con):
        return None
    row = con.execute(
        "SELECT state_value FROM companion_watcher_state WHERE state_key = ? LIMIT 1",
        [key],
    ).fetchone()
    return None if row is None else str(row[0])


def watcher_state_set(con: LockedConnection, key: str, value: str) -> None:
    init_evidence_index_schema(con)
    con.execute(
        "INSERT INTO companion_watcher_state (state_key, state_value) "
        "VALUES (?, ?) ON CONFLICT DO UPDATE SET state_value = excluded.state_value",
        [key, value],
    )
