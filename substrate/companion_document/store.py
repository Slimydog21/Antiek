"""The owner-safe evidence store and the refresh receipt row (LB-9a).

THREAD-CONTRACT §1.12 (signed rev 8.10) admits the refs-only evidence base
only with an owner-safe id: the owner in the id material, or the key
``(owner_user_id, evidence_id)``. This store does both (LB-9 spec D1):

- the id material is ``companion_document.v1``, owner, scope, scope id, kind
  and anchor, joined by ``\\x1f``;
- the anchor is a pointer, ``node:<node_id>`` or ``event:<event_id>#<i>``,
  never text, so a withheld entry's id cannot confirm a guess at its words;
- the key is ``(owner_user_id, evidence_id)``;
- scope and scope id are in the material because one node can sit in a
  project and a document of the same owner.

The tables are LB-9a's own, ``companion_document_evidence`` and
``companion_document_receipts``. #3514 is live on main: its routes read and
write its own ``evidence_index``, which is keyed on ``evidence_id`` alone and
mints the id from kind, claim text and refs with no owner, so a second owner
refreshing the same document hits ``Duplicate key "evidence_id: ev-…"``
(compws R2, lane A's C1). LB-9a never reads, writes, renames or drops that
table; it stands beside it. LB-9d retires #3514's table and routes in one
reviewed change. A table under LB-9a's own name with any other shape is
refused, never written into.

Rows hold refs only. There is no text column: ``text_sha256`` is the
server-side hash of the node label (64 hex digits, checked by the DDL too)
and is never serialised to a client.

Writes take a ``connect_write`` connection and land in one transaction:
the scope's old rows go, the new rows and the receipt row arrive, or nothing
changes (D17 step 3). Reads take any connection, run no DDL, and answer
empty until a refresh has created the tables.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, get_args

from runtime.db_lock import LockedConnection

EntryScope = Literal["project", "document"]
EntryKind = Literal["claim", "open_question", "insight"]

SCOPES: Final[tuple[EntryScope, ...]] = get_args(EntryScope)
ENTRY_KINDS: Final[tuple[EntryKind, ...]] = get_args(EntryKind)

#: The first element of every id's material. Changing any part of the
#: material changes every id, so it is a reviewed change with a new version.
ID_MATERIAL_VERSION: Final = "companion_document.v1"

#: LB-9a's own tables. They never share a name with #3514's live
#: ``evidence_index`` or any of its other tables.
EVIDENCE_TABLE: Final = "companion_document_evidence"
RECEIPTS_TABLE: Final = "companion_document_receipts"

# Stored strings back to their literal types; the DDL's CHECKs keep the
# stored values inside these, so a KeyError here is a corrupt row.
_SCOPE_OF: Final[dict[str, EntryScope]] = {s: s for s in SCOPES}
_KIND_OF: Final[dict[str, EntryKind]] = {k: k for k in ENTRY_KINDS}

_ANCHOR = re.compile(r"node:[^\s\x1f#]{1,256}|event:[^\s\x1f#]{1,256}#\d{1,6}")
_SHA256 = re.compile(r"[0-9a-f]{64}")

EVIDENCE_DDL: Final = """
CREATE TABLE IF NOT EXISTS companion_document_evidence (
  owner_user_id VARCHAR NOT NULL,
  evidence_id VARCHAR NOT NULL,
  scope VARCHAR NOT NULL CHECK (scope IN ('project', 'document')),
  scope_id VARCHAR NOT NULL,
  kind VARCHAR NOT NULL CHECK (kind IN ('claim', 'open_question', 'insight')),
  anchor VARCHAR NOT NULL CHECK (
    regexp_full_match(anchor, '(node:[^\\s#]{1,256})|(event:[^\\s#]{1,256}#[0-9]{1,6})')
  ),
  thread_ids_json VARCHAR NOT NULL,
  doc_ids_json VARCHAR NOT NULL,
  pins_json VARCHAR NOT NULL,
  process_thread_id VARCHAR,
  process_event_id VARCHAR,
  confidence VARCHAR,
  updated_at VARCHAR,
  text_sha256 VARCHAR CHECK (text_sha256 IS NULL OR regexp_full_match(text_sha256, '[0-9a-f]{64}')),
  refresh_event_id VARCHAR NOT NULL,
  PRIMARY KEY (owner_user_id, evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_companion_document_evidence_scope
  ON companion_document_evidence(owner_user_id, scope, scope_id);
"""

RECEIPTS_DDL: Final = """
CREATE TABLE IF NOT EXISTS companion_document_receipts (
  owner_user_id VARCHAR NOT NULL,
  scope VARCHAR NOT NULL CHECK (scope IN ('project', 'document')),
  scope_id VARCHAR NOT NULL,
  refresh_event_id VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL,
  covered_json VARCHAR NOT NULL,
  positions_json VARCHAR NOT NULL,
  membership_digest VARCHAR NOT NULL,
  reading_baseline_json VARCHAR NOT NULL,
  refreshed_at VARCHAR NOT NULL,
  PRIMARY KEY (owner_user_id, scope, scope_id)
);
"""

_COLUMNS: Final = (
    "owner_user_id, evidence_id, scope, scope_id, kind, anchor, thread_ids_json, doc_ids_json, "
    "pins_json, process_thread_id, process_event_id, confidence, updated_at, text_sha256, refresh_event_id"
)
_CURRENT_KEY: Final = ["owner_user_id", "evidence_id"]


@dataclass(frozen=True, slots=True)
class SourcePin:
    """One grounding pointer of an entry's node and the document it reaches;
    ``document_id`` is None when the pointer cannot be followed."""

    kind: str
    id: str
    document_id: str | None


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """What a refresh writes for one entry: refs and values, never text."""

    kind: EntryKind
    anchor: str
    thread_ids: tuple[str, ...]
    doc_ids: tuple[str, ...]
    pins: tuple[SourcePin, ...]
    process_thread_id: str | None
    process_event_id: str | None
    confidence: str | None
    updated_at: str | None
    text_sha256: str | None


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    """One stored row: an entry under its owner, scope and refresh."""

    owner_user_id: str
    evidence_id: str
    scope: EntryScope
    scope_id: str
    refresh_event_id: str
    entry: EvidenceEntry


@dataclass(frozen=True, slots=True)
class CompanionDocumentReceipt:
    """The DB index of one refresh receipt and its staleness baselines (D2).

    ``covered`` maps each summarised thread to its ``through_event_id``;
    ``positions`` holds each thread's event count at refresh, since event ids
    are not ordered; ``reading_baseline`` holds the watched reading counts.
    A GET trusts the rows only when ``refresh_event_id`` is in the receipt
    log, which is LB-9b and LB-9c's check, not this store's."""

    owner_user_id: str
    scope: EntryScope
    scope_id: str
    refresh_event_id: str
    content_hash: str
    covered: Mapping[str, str]
    positions: Mapping[str, int]
    membership_digest: str
    reading_baseline: Mapping[str, int]
    refreshed_at: str


def _require_part(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x1f" in value:
        raise ValueError(f"{name} must not contain the id-material separator")


def _require_scope(scope: str, scope_id: str, owner_user_id: str) -> None:
    _require_part("owner_user_id", owner_user_id)
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, not {scope!r}")
    _require_part("scope_id", scope_id)


def entry_id(
    *, owner_user_id: str, scope: EntryScope, scope_id: str, kind: EntryKind, anchor: str
) -> str:
    """The owner-safe entry id (``entry_id = evidence_id``, TC §1.12, D1)."""
    _require_scope(scope, scope_id, owner_user_id)
    if kind not in ENTRY_KINDS:
        raise ValueError(f"kind must be one of {ENTRY_KINDS}, not {kind!r}")
    if not isinstance(anchor, str) or not _ANCHOR.fullmatch(anchor):
        raise ValueError(
            "anchor must be a pointer, node:<node_id> or event:<event_id>#<i>, never text"
        )
    material = "\x1f".join([ID_MATERIAL_VERSION, owner_user_id, scope, scope_id, kind, anchor])
    return "ev-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def table_exists(con: Any, table: str) -> bool:
    """Whether ``table`` exists. Read paths use this instead of running DDL."""
    row = con.execute(
        "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [table]
    ).fetchone()
    return row is not None


def _columns(con: Any, table: str) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [table]
    ).fetchall()
    return {str(r[0]) for r in rows}


def _primary_key(con: Any, table: str) -> list[str]:
    row = con.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY' LIMIT 1",
        [table],
    ).fetchone()
    return [] if row is None else [str(c) for c in row[0]]


def _current_shape(con: Any) -> bool:
    return _primary_key(con, EVIDENCE_TABLE) == _CURRENT_KEY and "refresh_event_id" in _columns(
        con, EVIDENCE_TABLE
    )


def init_companion_document_schema(con: LockedConnection) -> None:
    """Create LB-9a's two tables (idempotent). Nothing else is touched:
    #3514's ``evidence_index`` and its other tables keep every column, row
    and index. A ``companion_document_evidence`` that exists with another
    shape is refused rather than written into."""
    if table_exists(con, EVIDENCE_TABLE) and not _current_shape(con):
        raise RuntimeError(
            f"{EVIDENCE_TABLE} exists without the owner-safe shape "
            "(key owner_user_id, evidence_id); refusing to write into it"
        )
    con.execute(EVIDENCE_DDL)
    con.execute(RECEIPTS_DDL)


def _dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_params(receipt: CompanionDocumentReceipt, entry: EvidenceEntry) -> tuple[Any, ...]:
    if entry.text_sha256 is not None and not _SHA256.fullmatch(entry.text_sha256):
        raise ValueError("text_sha256 must be 64 lowercase hex digits (a hash, never the text)")
    evidence_id = entry_id(
        owner_user_id=receipt.owner_user_id,
        scope=receipt.scope,
        scope_id=receipt.scope_id,
        kind=entry.kind,
        anchor=entry.anchor,
    )
    return (
        receipt.owner_user_id,
        evidence_id,
        receipt.scope,
        receipt.scope_id,
        entry.kind,
        entry.anchor,
        _dumps(list(entry.thread_ids)),
        _dumps(list(entry.doc_ids)),
        _dumps([[p.kind, p.id, p.document_id] for p in entry.pins]),
        entry.process_thread_id,
        entry.process_event_id,
        entry.confidence,
        entry.updated_at,
        entry.text_sha256,
        receipt.refresh_event_id,
    )


def _require_receipt(receipt: CompanionDocumentReceipt) -> None:
    _require_scope(receipt.scope, receipt.scope_id, receipt.owner_user_id)
    _require_part("refresh_event_id", receipt.refresh_event_id)


def upsert_receipt(con: LockedConnection, receipt: CompanionDocumentReceipt) -> None:
    """Write the receipt row for ``(owner, scope, scope_id)``, replacing the
    previous one. ``replace_scope`` calls this inside its transaction."""
    _require_receipt(receipt)
    con.execute(
        "INSERT INTO companion_document_receipts (owner_user_id, scope, scope_id, refresh_event_id, "
        "content_hash, covered_json, positions_json, membership_digest, reading_baseline_json, refreshed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (owner_user_id, scope, scope_id) DO UPDATE SET "
        "refresh_event_id = excluded.refresh_event_id, content_hash = excluded.content_hash, "
        "covered_json = excluded.covered_json, positions_json = excluded.positions_json, "
        "membership_digest = excluded.membership_digest, "
        "reading_baseline_json = excluded.reading_baseline_json, refreshed_at = excluded.refreshed_at",
        [
            receipt.owner_user_id,
            receipt.scope,
            receipt.scope_id,
            receipt.refresh_event_id,
            receipt.content_hash,
            _dumps(dict(receipt.covered)),
            _dumps(dict(receipt.positions)),
            receipt.membership_digest,
            _dumps(dict(receipt.reading_baseline)),
            receipt.refreshed_at,
        ],
    )


def replace_scope(
    con: LockedConnection, receipt: CompanionDocumentReceipt, entries: Sequence[EvidenceEntry]
) -> tuple[EvidenceRow, ...]:
    """Replace one owner's rows for one scope with ``entries`` and write the
    receipt, in one transaction. Only rows matching the receipt's owner,
    scope and scope id are deleted. Every entry is validated before the
    transaction opens; a failure inside it (an entry repeating another's
    kind and anchor repeats its id, which the key refuses) rolls back and
    the previous generation stands."""
    _require_receipt(receipt)
    params = [_row_params(receipt, e) for e in entries]
    init_companion_document_schema(con)
    with con.transaction():
        con.execute(
            f"DELETE FROM {EVIDENCE_TABLE} WHERE owner_user_id = ? AND scope = ? AND scope_id = ?",
            [receipt.owner_user_id, receipt.scope, receipt.scope_id],
        )
        if params:
            con.executemany(
                f"INSERT INTO {EVIDENCE_TABLE} ({_COLUMNS}) VALUES ({', '.join('?' * 15)})",
                params,
            )
        upsert_receipt(con, receipt)
    return tuple(
        sorted(
            (
                EvidenceRow(
                    owner_user_id=receipt.owner_user_id,
                    evidence_id=str(p[1]),
                    scope=receipt.scope,
                    scope_id=receipt.scope_id,
                    refresh_event_id=receipt.refresh_event_id,
                    entry=e,
                )
                for p, e in zip(params, entries, strict=True)
            ),
            key=lambda r: r.evidence_id,
        )
    )


def _to_row(r: Sequence[Any]) -> EvidenceRow:
    pins = tuple(
        SourcePin(kind=str(k), id=str(i), document_id=None if d is None else str(d))
        for k, i, d in json.loads(r[8])
    )
    return EvidenceRow(
        owner_user_id=str(r[0]),
        evidence_id=str(r[1]),
        scope=_SCOPE_OF[str(r[2])],
        scope_id=str(r[3]),
        refresh_event_id=str(r[14]),
        entry=EvidenceEntry(
            kind=_KIND_OF[str(r[4])],
            anchor=str(r[5]),
            thread_ids=tuple(str(t) for t in json.loads(r[6])),
            doc_ids=tuple(str(d) for d in json.loads(r[7])),
            pins=pins,
            process_thread_id=None if r[9] is None else str(r[9]),
            process_event_id=None if r[10] is None else str(r[10]),
            confidence=None if r[11] is None else str(r[11]),
            updated_at=None if r[12] is None else str(r[12]),
            text_sha256=None if r[13] is None else str(r[13]),
        ),
    )


def _readable(con: Any) -> bool:
    return table_exists(con, EVIDENCE_TABLE) and _current_shape(con)


def read_scope(
    con: Any, *, owner_user_id: str, scope: EntryScope, scope_id: str
) -> tuple[EvidenceRow, ...]:
    """One owner's rows for one scope, sorted by id. Empty before the first
    refresh. Never reads #3514's ``evidence_index``."""
    if not _readable(con):
        return ()
    rows = con.execute(
        f"SELECT {_COLUMNS} FROM {EVIDENCE_TABLE} "
        "WHERE owner_user_id = ? AND scope = ? AND scope_id = ? ORDER BY evidence_id",
        [owner_user_id, scope, scope_id],
    ).fetchall()
    return tuple(_to_row(r) for r in rows)


def resolve(con: Any, owner_user_id: str, entry_id: str) -> EvidenceRow | None:
    """One owner's row for ``entry_id``, or None. Another owner's row with
    the same id is never returned."""
    if not _readable(con):
        return None
    row = con.execute(
        f"SELECT {_COLUMNS} FROM {EVIDENCE_TABLE} WHERE owner_user_id = ? AND evidence_id = ?",
        [owner_user_id, entry_id],
    ).fetchone()
    return None if row is None else _to_row(row)


def read_receipt(
    con: Any, *, owner_user_id: str, scope: EntryScope, scope_id: str
) -> CompanionDocumentReceipt | None:
    """The receipt row for ``(owner, scope, scope_id)``, or None when that
    scope was never refreshed."""
    if not table_exists(con, RECEIPTS_TABLE):
        return None
    row = con.execute(
        "SELECT refresh_event_id, content_hash, covered_json, positions_json, membership_digest, "
        "reading_baseline_json, refreshed_at FROM companion_document_receipts "
        "WHERE owner_user_id = ? AND scope = ? AND scope_id = ?",
        [owner_user_id, scope, scope_id],
    ).fetchone()
    if row is None:
        return None
    return CompanionDocumentReceipt(
        owner_user_id=owner_user_id,
        scope=scope,
        scope_id=scope_id,
        refresh_event_id=str(row[0]),
        content_hash=str(row[1]),
        covered={str(k): str(v) for k, v in json.loads(row[2]).items()},
        positions={str(k): int(v) for k, v in json.loads(row[3]).items()},
        membership_digest=str(row[4]),
        reading_baseline={str(k): int(v) for k, v in json.loads(row[5]).items()},
        refreshed_at=str(row[6]),
    )


__all__ = [
    "ENTRY_KINDS",
    "EVIDENCE_DDL",
    "EVIDENCE_TABLE",
    "ID_MATERIAL_VERSION",
    "RECEIPTS_DDL",
    "RECEIPTS_TABLE",
    "SCOPES",
    "CompanionDocumentReceipt",
    "EntryKind",
    "EntryScope",
    "EvidenceEntry",
    "EvidenceRow",
    "SourcePin",
    "entry_id",
    "init_companion_document_schema",
    "read_receipt",
    "read_scope",
    "replace_scope",
    "resolve",
    "table_exists",
    "upsert_receipt",
]
