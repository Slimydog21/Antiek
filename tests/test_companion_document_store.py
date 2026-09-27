"""The owner-safe ``evidence_index`` and its receipt row (LB-9a; THREAD-CONTRACT
§1.12, signed rev 8.10). T-a1 to T-a8.

#3514 keyed ``evidence_index`` on ``evidence_id`` alone and minted the id with
no owner in it, so the second owner to refresh the same document scope hit
``Duplicate key "evidence_id: ev-…"`` (compws R2), and ``resolve`` answered
one owner's id to anyone. These tests seed that DDL where the spec asks for
it, prove it still collides (so the control is live), and then prove the new
store does not.

Every test runs against a real DuckDB file through ``connect_write``; nothing
is mocked.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import LockedConnection, connect_read, connect_write
from substrate.companion_document.store import (
    ENTRY_KINDS,
    ID_MATERIAL_VERSION,
    LEGACY_3514_TABLE,
    SCOPES,
    CompanionDocumentReceipt,
    EvidenceEntry,
    SourcePin,
    entry_id,
    init_companion_document_schema,
    read_receipt,
    read_scope,
    replace_scope,
    resolve,
    table_exists,
    upsert_receipt,
)

# #3514's DDL, verbatim from feat/companion-spr03 @ f87a4db64,
# substrate/companions/evidence_index.py:59-73.
DDL_3514 = """
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

# The same R2 id both owners minted under #3514 (compws R2).
R2_ID = "ev-585194df9dd251baa334b5a9"
SENTINEL_LABEL = "SENTINEL-LABEL Bridge decks fail at the joints qz7"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "lb9a-store.duckdb")


@pytest.fixture
def con(db: str) -> Iterator[LockedConnection]:
    with connect_write(db, purpose="test/lb9a-store", keepalive_s=0) as c:
        yield c


def _entry(
    anchor: str = "node:ins-bridge-1", *, kind: str = "insight", text: str | None = None
) -> EvidenceEntry:
    return EvidenceEntry(
        kind=kind,  # type: ignore[arg-type]
        anchor=anchor,
        thread_ids=("inv-1",),
        doc_ids=("doc-1",),
        pins=(SourcePin(kind="node", id=anchor.partition(":")[2] or anchor, document_id="doc-1"),),
        process_thread_id="inv-1",
        process_event_id="evt-1",
        confidence="high",
        updated_at="2026-09-27T00:00:00Z",
        text_sha256=None if text is None else _sha(text),
    )


def _receipt(
    owner: str, scope_id: str = "doc-1", *, scope: str = "document", event: str = "rcpt-1"
) -> CompanionDocumentReceipt:
    return CompanionDocumentReceipt(
        owner_user_id=owner,
        scope=scope,  # type: ignore[arg-type]
        scope_id=scope_id,
        refresh_event_id=event,
        content_hash="c" * 64,
        covered={"inv-1": "evt-1"},
        positions={"inv-1": 3},
        membership_digest="d" * 64,
        reading_baseline={"read-doc-1": 0},
        refreshed_at="2026-09-27T00:00:01Z",
    )


def _all_rows(c: LockedConnection) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = c.execute(
        "SELECT owner_user_id, scope, scope_id, evidence_id FROM evidence_index ORDER BY 1, 2, 3, 4"
    ).fetchall()
    return rows


def _primary_key(c: LockedConnection, table: str) -> list[str]:
    row = c.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'",
        [table],
    ).fetchone()
    assert row is not None, f"{table} has no primary key"
    return list(row[0])


# ── The control: #3514's key really does collide (R2) ────────────────────


def test_r2_control_3514_key_collides_across_owners(con: LockedConnection) -> None:
    """The red state, ported from the compws repro as an assertion: under
    #3514's DDL the second owner's insert of the same id fails. If this ever
    stops raising, the tests below that use this DDL prove nothing."""
    con.execute(DDL_3514)
    insert = (
        "INSERT INTO evidence_index (evidence_id, owner_user_id, scope, scope_id, kind, refs_json, rebuilt_at) "
        "VALUES (?, ?, 'document', 'doc-1', 'claim', '[]', 't')"
    )
    con.execute(insert, [R2_ID, "owner-a"])
    with pytest.raises(duckdb.ConstraintException, match=f'Duplicate key "evidence_id: {R2_ID}"'):
        con.execute(insert, [R2_ID, "owner-b"])


# ── T-a1 ──────────────────────────────────────────────────────────────────


def test_r2_second_owner_refresh_of_same_scope_does_not_collide(con: LockedConnection) -> None:
    """T-a1: owner-a and then owner-b replace document scope doc-1 with
    identical pins; both succeed, and each reads only its own rows."""
    a = replace_scope(con, _receipt("owner-a"), [_entry()])
    b = replace_scope(con, _receipt("owner-b"), [_entry()])
    assert len(a) == len(b) == 1
    rows_a = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    rows_b = read_scope(con, owner_user_id="owner-b", scope="document", scope_id="doc-1")
    assert [r.owner_user_id for r in rows_a] == ["owner-a"]
    assert [r.owner_user_id for r in rows_b] == ["owner-b"]
    assert rows_a[0].entry == rows_b[0].entry == _entry()
    assert rows_a[0].evidence_id != rows_b[0].evidence_id
    assert len(_all_rows(con)) == 2


# ── T-a2 ──────────────────────────────────────────────────────────────────


def test_entry_id_material_is_the_documented_formula() -> None:
    """T-a2 (pin): the id is exactly D1's material, so any change to it is a
    reviewed change, not drift."""
    material = "\x1f".join(
        [ID_MATERIAL_VERSION, "owner-a", "document", "doc-1", "insight", "node:n1"]
    )
    expected = "ev-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    assert ID_MATERIAL_VERSION == "companion_document.v1"
    assert (
        entry_id(
            owner_user_id="owner-a",
            scope="document",
            scope_id="doc-1",
            kind="insight",
            anchor="node:n1",
        )
        == expected
    )


def test_entry_id_differs_by_owner_scope_scope_id_kind_and_anchor() -> None:
    """T-a2: every part of the material moves the id."""
    base = {
        "owner_user_id": "owner-a",
        "scope": "document",
        "scope_id": "doc-1",
        "kind": "insight",
        "anchor": "node:n1",
    }
    variants = [
        base,
        {**base, "owner_user_id": "owner-b"},
        {**base, "scope": "project"},
        {**base, "scope_id": "doc-2"},
        {**base, "kind": "open_question"},
        {**base, "anchor": "node:n2"},
    ]
    ids = [entry_id(**v) for v in variants]  # type: ignore[arg-type]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("ev-") and len(i) == 27 for i in ids)


def test_entry_id_is_unchanged_when_the_node_text_changes(con: LockedConnection) -> None:
    """T-a2: the id never keys on text. Refreshing the same node with a new
    label (a new text hash) keeps the id; only the server-only hash moves."""
    first = replace_scope(
        con, _receipt("owner-a"), [_entry(text="Bridge decks fail at the joints.")]
    )
    second = replace_scope(
        con,
        _receipt("owner-a", event="rcpt-2"),
        [_entry(text="Bridge decks fail at the welded joints.")],
    )
    assert first[0].evidence_id == second[0].evidence_id
    assert first[0].entry.text_sha256 != second[0].entry.text_sha256


@pytest.mark.parametrize(
    "bad",
    [
        {"owner_user_id": ""},
        {"scope": "workspace"},
        {"scope_id": ""},
        {"kind": "evidence"},
        {"anchor": "Bridge decks fail at the joints"},
        {"anchor": "node:"},
        {"anchor": "event:evt-1"},
        {"anchor": "node:n1\x1fdocument"},
        {"scope_id": "doc\x1f1"},
    ],
)
def test_entry_id_refuses_malformed_material(bad: dict[str, str]) -> None:
    base = {
        "owner_user_id": "owner-a",
        "scope": "document",
        "scope_id": "doc-1",
        "kind": "insight",
        "anchor": "node:n1",
    }
    with pytest.raises(ValueError):
        entry_id(**{**base, **bad})  # type: ignore[arg-type]


def test_entry_id_accepts_the_claim_anchor_form() -> None:
    assert entry_id(
        owner_user_id="owner-a",
        scope="project",
        scope_id="p-1",
        kind="claim",
        anchor="event:evt-9#2",
    ).startswith("ev-")
    assert SCOPES == ("project", "document")
    assert ENTRY_KINDS == ("claim", "open_question", "insight")


# ── T-a3 ──────────────────────────────────────────────────────────────────


def test_same_evidence_id_for_two_owners_is_admitted_by_the_key(con: LockedConnection) -> None:
    """T-a3: the key is (owner_user_id, evidence_id), so the R2 id stored for
    two owners is two rows, not a constraint error."""
    init_companion_document_schema(con)
    assert _primary_key(con, "evidence_index") == ["owner_user_id", "evidence_id"]
    insert = (
        "INSERT INTO evidence_index (owner_user_id, evidence_id, scope, scope_id, kind, anchor, "
        "thread_ids_json, doc_ids_json, pins_json, refresh_event_id) "
        "VALUES (?, ?, 'document', 'doc-1', 'claim', 'node:n1', '[]', '[]', '[]', 'rcpt-1')"
    )
    con.execute(insert, ["owner-a", R2_ID])
    con.execute(insert, ["owner-b", R2_ID])
    assert _all_rows(con) == [
        ("owner-a", "document", "doc-1", R2_ID),
        ("owner-b", "document", "doc-1", R2_ID),
    ]
    with pytest.raises(duckdb.ConstraintException):
        con.execute(insert, ["owner-a", R2_ID])


# ── T-a4 ──────────────────────────────────────────────────────────────────


def test_resolve_is_owner_scoped(con: LockedConnection) -> None:
    """T-a4: resolve(owner_b, id_a) is None, even when owner-b holds a row
    with that very id (the raw-SQL case the key now admits)."""
    (row_a,) = replace_scope(con, _receipt("owner-a"), [_entry()])
    assert resolve(con, "owner-a", row_a.evidence_id) == row_a
    assert resolve(con, "owner-b", row_a.evidence_id) is None
    replace_scope(con, _receipt("owner-b"), [_entry()])
    assert resolve(con, "owner-b", row_a.evidence_id) is None
    con.execute(
        "INSERT INTO evidence_index (owner_user_id, evidence_id, scope, scope_id, kind, anchor, "
        "thread_ids_json, doc_ids_json, pins_json, refresh_event_id) "
        "VALUES ('owner-b', ?, 'document', 'doc-7', 'claim', 'node:other', '[]', '[]', '[]', 'rcpt-x')",
        [row_a.evidence_id],
    )
    got_b = resolve(con, "owner-b", row_a.evidence_id)
    assert got_b is not None and got_b.owner_user_id == "owner-b" and got_b.scope_id == "doc-7"
    assert resolve(con, "owner-a", row_a.evidence_id) == row_a
    assert resolve(con, "owner-a", "ev-000000000000000000000000") is None


# ── T-a5 ──────────────────────────────────────────────────────────────────


def test_refresh_is_scoped_by_owner_scope_and_scope_id(con: LockedConnection) -> None:
    """T-a5: owner-b's refresh keeps owner-a's rows; a refresh of doc-2 keeps
    doc-1's; a project scope and a document scope sharing an id are separate."""
    replace_scope(con, _receipt("owner-a", "doc-1"), [_entry("node:a1"), _entry("node:a2")])
    replace_scope(con, _receipt("owner-a", "doc-2"), [_entry("node:a3")])
    replace_scope(con, _receipt("owner-a", "doc-1", scope="project"), [_entry("node:a4")])
    before = _all_rows(con)
    assert len(before) == 4

    replace_scope(con, _receipt("owner-b", "doc-1"), [])
    assert _all_rows(con) == before

    replace_scope(con, _receipt("owner-a", "doc-2"), [])
    assert [r for r in _all_rows(con) if r[2] == "doc-1"] == [r for r in before if r[2] == "doc-1"]
    assert read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-2") == ()

    replace_scope(con, _receipt("owner-a", "doc-1", scope="project"), [])
    doc_rows = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    assert sorted(r.entry.anchor for r in doc_rows) == ["node:a1", "node:a2"]


def test_refresh_replaces_the_scope_it_names(con: LockedConnection) -> None:
    replace_scope(con, _receipt("owner-a"), [_entry("node:a1"), _entry("node:a2")])
    replace_scope(con, _receipt("owner-a", event="rcpt-2"), [_entry("node:a3")])
    rows = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    assert [r.entry.anchor for r in rows] == ["node:a3"]
    assert rows[0].refresh_event_id == "rcpt-2"


# ── T-a6 ──────────────────────────────────────────────────────────────────


def test_failed_insert_mid_batch_keeps_the_previous_generation(con: LockedConnection) -> None:
    """T-a6: the DELETE, the inserts and the receipt land together or not at
    all. The third entry repeats the first's (kind, anchor), so it repeats
    its id, and the primary key refuses it after the DELETE and the first
    inserts have run."""
    gen1 = replace_scope(con, _receipt("owner-a"), [_entry("node:a1"), _entry("node:a2")])
    receipt1 = read_receipt(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    with pytest.raises(duckdb.ConstraintException):
        replace_scope(
            con,
            _receipt("owner-a", event="rcpt-2"),
            [_entry("node:b1"), _entry("node:b2"), _entry("node:b1")],
        )
    assert read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == gen1
    assert (
        read_receipt(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == receipt1
    )
    assert not con.in_explicit_transaction
    # The connection is still usable, and a clean retry lands.
    gen2 = replace_scope(con, _receipt("owner-a", event="rcpt-3"), [_entry("node:b1")])
    assert read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == gen2


def test_malformed_entry_writes_nothing(con: LockedConnection) -> None:
    """A receipt and its rows are one generation; a malformed entry is refused
    before the transaction opens, and the previous generation stands."""
    replace_scope(con, _receipt("owner-a"), [_entry("node:a1")])
    before = _all_rows(con)
    text_as_hash = EvidenceEntry(
        kind="insight",
        anchor="node:a1",
        thread_ids=(),
        doc_ids=(),
        pins=(),
        process_thread_id=None,
        process_event_id=None,
        confidence=None,
        updated_at=None,
        text_sha256="Bridge decks fail at the joints",
    )
    for bad in (_entry("Bridge decks fail at the joints"), text_as_hash):
        with pytest.raises(ValueError):
            replace_scope(con, _receipt("owner-a", event="rcpt-2"), [_entry("node:a2"), bad])
    assert _all_rows(con) == before
    assert read_receipt(
        con, owner_user_id="owner-a", scope="document", scope_id="doc-1"
    ) == _receipt("owner-a")


# ── T-a7 ──────────────────────────────────────────────────────────────────


def test_no_column_stores_text(con: LockedConnection) -> None:
    """T-a7: a refresh built from a node whose label is a sentinel stores the
    label in no VARCHAR column of either table. The positive control (the
    node id IS found) proves the scan reads every row and column."""
    entry = _entry("node:ins-sentinel-node", text=SENTINEL_LABEL)
    replace_scope(con, _receipt("owner-a"), [entry])
    found_label: list[tuple[str, str]] = []
    found_pointer: list[tuple[str, str]] = []
    for table in ("evidence_index", "companion_document_receipts"):
        columns = [
            r[0]
            for r in con.execute(
                "SELECT column_name FROM duckdb_columns() WHERE table_name = ? AND data_type = 'VARCHAR'",
                [table],
            ).fetchall()
        ]
        assert columns, f"{table} has no VARCHAR columns to scan"
        assert not {"text", "label", "canonical_label", "body", "title"} & set(columns)
        for column in columns:
            for (value,) in con.execute(f'SELECT "{column}" FROM {table}').fetchall():
                if value is None:
                    continue
                if SENTINEL_LABEL in value or "Bridge decks" in value:
                    found_label.append((table, column))
                if "ins-sentinel-node" in value:
                    found_pointer.append((table, column))
    assert found_label == []
    assert ("evidence_index", "anchor") in found_pointer
    (stored,) = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    assert stored.entry.text_sha256 == _sha(SENTINEL_LABEL)


def test_text_hash_column_refuses_text_even_through_raw_sql(con: LockedConnection) -> None:
    init_companion_document_schema(con)
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO evidence_index (owner_user_id, evidence_id, scope, scope_id, kind, anchor, "
            "thread_ids_json, doc_ids_json, pins_json, refresh_event_id, text_sha256) "
            "VALUES ('owner-a', 'ev-1', 'document', 'doc-1', 'insight', 'node:n1', '[]', '[]', '[]', 'r', ?)",
            [SENTINEL_LABEL],
        )
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO evidence_index (owner_user_id, evidence_id, scope, scope_id, kind, anchor, "
            "thread_ids_json, doc_ids_json, pins_json, refresh_event_id) "
            "VALUES ('owner-a', 'ev-1', 'document', 'doc-1', 'insight', ?, '[]', '[]', '[]', 'r')",
            [SENTINEL_LABEL],
        )


# ── T-a8 ──────────────────────────────────────────────────────────────────


def test_init_migrates_the_3514_shape_and_r2_then_passes(con: LockedConnection) -> None:
    """T-a8: #3514's DDL is seeded (with a row), init runs, the key becomes
    (owner_user_id, evidence_id), the old rows survive under the legacy
    name, and T-a1's two-owner refresh then passes on that database."""
    con.execute(DDL_3514)
    con.execute(
        "INSERT INTO evidence_index (evidence_id, owner_user_id, scope, scope_id, kind, refs_json, rebuilt_at) "
        "VALUES (?, 'owner-a', 'document', 'doc-1', 'claim', '[\"node:n1\"]', 't')",
        [R2_ID],
    )
    assert _primary_key(con, "evidence_index") == ["evidence_id"]

    init_companion_document_schema(con)
    assert _primary_key(con, "evidence_index") == ["owner_user_id", "evidence_id"]
    assert table_exists(con, LEGACY_3514_TABLE)
    assert _primary_key(con, LEGACY_3514_TABLE) == ["evidence_id"]
    assert con.execute(
        f"SELECT evidence_id, owner_user_id FROM {LEGACY_3514_TABLE}"
    ).fetchall() == [(R2_ID, "owner-a")]
    assert _all_rows(con) == []

    # Idempotent: a second init changes nothing.
    init_companion_document_schema(con)
    assert _primary_key(con, "evidence_index") == ["owner_user_id", "evidence_id"]

    replace_scope(con, _receipt("owner-a"), [_entry()])
    replace_scope(con, _receipt("owner-b"), [_entry()])
    assert [r[0] for r in _all_rows(con)] == ["owner-a", "owner-b"]


def test_replace_scope_on_a_3514_database_migrates_first(con: LockedConnection) -> None:
    """The write path initialises before it writes (D17 step 2), so a first
    refresh against a #3514 database does not collide either."""
    con.execute(DDL_3514)
    replace_scope(con, _receipt("owner-a"), [_entry()])
    replace_scope(con, _receipt("owner-b"), [_entry()])
    assert _primary_key(con, "evidence_index") == ["owner_user_id", "evidence_id"]
    assert len(_all_rows(con)) == 2


def test_init_refuses_an_evidence_index_of_unknown_shape(con: LockedConnection) -> None:
    """Neither #3514's shape nor ours: refuse rather than guess."""
    con.execute("CREATE TABLE evidence_index (evidence_id VARCHAR PRIMARY KEY, payload VARCHAR)")
    with pytest.raises(RuntimeError, match="evidence_index"):
        init_companion_document_schema(con)
    assert _primary_key(con, "evidence_index") == ["evidence_id"]
    assert not table_exists(con, LEGACY_3514_TABLE)


def test_read_paths_before_migration_see_nothing(db: str) -> None:
    """A read connection never runs DDL: before any refresh, and on a
    database still holding #3514's shape, the read helpers answer empty."""
    with connect_write(db, purpose="test/seed-3514", keepalive_s=0) as c:
        c.execute("CREATE TABLE seed_marker (x INTEGER)")
    reader = connect_read(db)
    try:
        assert read_scope(reader, owner_user_id="owner-a", scope="document", scope_id="doc-1") == ()
        assert resolve(reader, "owner-a", R2_ID) is None
        assert (
            read_receipt(reader, owner_user_id="owner-a", scope="document", scope_id="doc-1")
            is None
        )
    finally:
        reader.close()
    with connect_write(db, purpose="test/seed-3514", keepalive_s=0) as c:
        c.execute(DDL_3514)
        c.execute(
            "INSERT INTO evidence_index (evidence_id, owner_user_id, scope, scope_id, kind, refs_json, rebuilt_at) "
            "VALUES (?, 'owner-a', 'document', 'doc-1', 'claim', '[]', 't')",
            [R2_ID],
        )
    reader = connect_read(db)
    try:
        assert read_scope(reader, owner_user_id="owner-a", scope="document", scope_id="doc-1") == ()
        assert resolve(reader, "owner-a", R2_ID) is None
        assert not table_exists(reader, "companion_document_receipts")
    finally:
        reader.close()


# ── Receipts (D2) ─────────────────────────────────────────────────────────


def test_receipt_round_trips_and_upserts_per_owner_scope(con: LockedConnection) -> None:
    replace_scope(con, _receipt("owner-a"), [_entry()])
    replace_scope(con, _receipt("owner-b"), [_entry()])
    assert read_receipt(
        con, owner_user_id="owner-a", scope="document", scope_id="doc-1"
    ) == _receipt("owner-a")
    newer = _receipt("owner-a", event="rcpt-9")
    upsert_receipt(con, newer)
    assert read_receipt(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == newer
    assert read_receipt(
        con, owner_user_id="owner-b", scope="document", scope_id="doc-1"
    ) == _receipt("owner-b")
    assert read_receipt(con, owner_user_id="owner-a", scope="project", scope_id="doc-1") is None
    assert _primary_key(con, "companion_document_receipts") == [
        "owner_user_id",
        "scope",
        "scope_id",
    ]
    stored = con.execute(
        "SELECT covered_json, positions_json, reading_baseline_json FROM companion_document_receipts "
        "WHERE owner_user_id = 'owner-b'"
    ).fetchone()
    assert stored is not None
    assert [json.loads(v) for v in stored] == [{"inv-1": "evt-1"}, {"inv-1": 3}, {"read-doc-1": 0}]


def test_rows_carry_their_refresh_event(con: LockedConnection) -> None:
    (row,) = replace_scope(con, _receipt("owner-a", event="rcpt-7"), [_entry()])
    assert row.refresh_event_id == "rcpt-7"
    assert read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == (row,)


def test_read_scope_is_sorted_and_round_trips_every_field(con: LockedConnection) -> None:
    entries = [_entry(f"node:n{i}", text=f"label {i}") for i in range(5)]
    written = replace_scope(con, _receipt("owner-a"), entries)
    read = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    assert read == written
    assert [r.evidence_id for r in read] == sorted(r.evidence_id for r in read)
    assert {r.entry for r in read} == set(entries)
