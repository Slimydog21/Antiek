"""The owner-safe evidence store and its receipt row (LB-9a; THREAD-CONTRACT
§1.12, signed rev 8.10). T-a1 to T-a8.

#3514 is live on main: ``substrate.companions.evidence_index`` keys its
``evidence_index`` table on ``evidence_id`` alone and mints the id with no
owner in it, so the second owner to refresh the same document scope hits
``Duplicate key "evidence_id: ev-…"`` (compws R2, lane A's C1), and its
``resolve`` answers one owner's id to anyone. The first test here pins that
live defect with main's own functions. LB-9a keeps its own tables,
``companion_document_evidence`` and ``companion_document_receipts``, beside
#3514's and never touches them; LB-9d retires #3514's table and routes in one
reviewed change.

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
    EVIDENCE_TABLE,
    ID_MATERIAL_VERSION,
    RECEIPTS_TABLE,
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
from substrate.companions import evidence_index as live_3514

# #3514's tables on main (substrate/companions/evidence_index.py DDL and
# WIRING_DDL). LB-9a must leave every one of them as it found it.
TABLES_3514 = (
    "evidence_index",
    "companion_rebuild_receipts",
    "companion_seen_triggers",
    "companion_seen_triggers_by_owner",
    "companion_watcher_state",
)

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
        "SELECT owner_user_id, scope, scope_id, evidence_id FROM companion_document_evidence "
        "ORDER BY 1, 2, 3, 4"
    ).fetchall()
    return rows


def _rows_3514(owner: str, eid: str, refs: list[str]) -> list[live_3514.EvidenceRow]:
    return [
        live_3514.EvidenceRow(
            evidence_id=eid,
            owner_user_id=owner,
            scope="document",
            scope_id="doc-1",
            kind="claim",
            refs=tuple(sorted(refs)),
            tombstone=False,
            rebuilt_at="2026-09-27T00:00:00Z",
        )
    ]


def _snapshot_3514(c: LockedConnection) -> dict[str, object]:
    """Every column, constraint, index and row of #3514's tables, in a
    stable order, so two snapshots compare equal only when nothing moved."""
    snap: dict[str, object] = {}
    for table in TABLES_3514:
        columns = c.execute(
            "SELECT column_name, data_type, is_nullable, column_default FROM duckdb_columns() "
            "WHERE table_name = ? ORDER BY column_index",
            [table],
        ).fetchall()
        constraints = c.execute(
            "SELECT constraint_type, constraint_column_names, expression FROM duckdb_constraints() "
            "WHERE table_name = ? ORDER BY constraint_index",
            [table],
        ).fetchall()
        indexes = c.execute(
            "SELECT index_name, sql FROM duckdb_indexes() WHERE table_name = ? ORDER BY index_name",
            [table],
        ).fetchall()
        rows = c.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()
        snap[table] = (columns, constraints, indexes, rows)
    return snap


def _primary_key(c: LockedConnection, table: str) -> list[str]:
    row = c.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'",
        [table],
    ).fetchone()
    assert row is not None, f"{table} has no primary key"
    return list(row[0])


# ── R2 on main: #3514's live store collides across owners ────────────────


def test_r2_live_3514_store_collides_across_owners_on_main(con: LockedConnection) -> None:
    """The compws R2 steps, run as an assertion through main's own #3514
    functions: owner-a and then owner-b rebuild document scope doc-1 with the
    same claim identity and refs. #3514's id has no owner and its key is
    ``evidence_id`` alone, so owner-b's rebuild raises, and #3514's
    ``resolve`` answers owner-a's row to anyone holding the id.

    This pins a LIVE defect (lane A's C1), not LB-9a behaviour. It is the
    reason LB-9a's store exists, and it goes when LB-9d retires #3514's
    table and routes. If #3514's key is fixed first, delete this test."""
    refs = ["node:ins-bridge-1", "inv:inv-1"]
    eid = live_3514.make_evidence_id("claim", "Bridge decks fail at the joints", refs)
    live_3514.rebuild_scope(
        con,
        owner_user_id="owner-a",
        scope="document",
        scope_id="doc-1",
        rows=_rows_3514("owner-a", eid, refs),
    )
    assert _primary_key(con, "evidence_index") == ["evidence_id"]
    with pytest.raises(duckdb.ConstraintException, match=f'Duplicate key "evidence_id: {eid}"'):
        live_3514.rebuild_scope(
            con,
            owner_user_id="owner-b",
            scope="document",
            scope_id="doc-1",
            rows=_rows_3514("owner-b", eid, refs),
        )
    leaked = live_3514.resolve(con, eid)
    assert leaked is not None and leaked.owner_user_id == "owner-a"


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
    assert (EVIDENCE_TABLE, RECEIPTS_TABLE) == (
        "companion_document_evidence",
        "companion_document_receipts",
    )
    assert _primary_key(con, "companion_document_evidence") == ["owner_user_id", "evidence_id"]
    # LB-9a's init creates only its own tables; #3514's name is not ours.
    assert not table_exists(con, "evidence_index")
    insert = (
        "INSERT INTO companion_document_evidence (owner_user_id, evidence_id, scope, scope_id, "
        "kind, anchor, "
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
        "INSERT INTO companion_document_evidence (owner_user_id, evidence_id, scope, scope_id, kind, "
        "anchor, thread_ids_json, doc_ids_json, pins_json, refresh_event_id) "
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
    for table in ("companion_document_evidence", "companion_document_receipts"):
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
    assert ("companion_document_evidence", "anchor") in found_pointer
    (stored,) = read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1")
    assert stored.entry.text_sha256 == _sha(SENTINEL_LABEL)


def test_text_hash_column_refuses_text_even_through_raw_sql(con: LockedConnection) -> None:
    init_companion_document_schema(con)
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO companion_document_evidence (owner_user_id, evidence_id, scope, scope_id, "
            "kind, anchor, thread_ids_json, doc_ids_json, pins_json, refresh_event_id, text_sha256) "
            "VALUES ('owner-a', 'ev-1', 'document', 'doc-1', 'insight', 'node:n1', '[]', '[]', '[]', 'r', ?)",
            [SENTINEL_LABEL],
        )
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO companion_document_evidence (owner_user_id, evidence_id, scope, scope_id, "
            "kind, anchor, thread_ids_json, doc_ids_json, pins_json, refresh_event_id) "
            "VALUES ('owner-a', 'ev-1', 'document', 'doc-1', 'insight', ?, '[]', '[]', '[]', 'r')",
            [SENTINEL_LABEL],
        )


# ── T-a8: beside #3514's live tables ─────────────────────────────────────


def _seed_3514(c: LockedConnection) -> str:
    """#3514's own schema and a generation of its own rows, written through
    main's #3514 functions: a claim for owner-a on doc-1, a receipt, a seen
    trigger and a watcher watermark."""
    refs = ["node:n1", "inv:inv-1"]
    eid = live_3514.make_evidence_id("claim", "Bridge decks fail at the joints", refs)
    live_3514.init_evidence_index_schema(c)
    live_3514.rebuild_scope(
        c,
        owner_user_id="owner-a",
        scope="document",
        scope_id="doc-1",
        rows=_rows_3514("owner-a", eid, refs),
    )
    live_3514.record_receipt(
        c,
        live_3514.RebuildReceipt(
            rebuild_id="rb-1",
            owner_user_id="owner-a",
            scope="document",
            scope_id="doc-1",
            trigger_event_ids=("evt-1",),
            rows_written=1,
            duration_ms=3,
            status="completed",
            error=None,
            rebuilt_at="2026-09-27T00:00:00Z",
        ),
    )
    live_3514.mark_triggers_seen(c, "owner-a", ["evt-1"], "2026-09-27T00:00:00Z")
    c.execute("INSERT INTO companion_seen_triggers (event_id, seen_at) VALUES ('evt-legacy', 't')")
    live_3514.watcher_state_set(c, "diligence_watermark", "w-1")
    return eid


def test_lb9a_schema_coexists_with_3514_and_leaves_it_byte_identical(
    con: LockedConnection,
) -> None:
    """T-a8: #3514's schema and rows are in place, as on main, where its
    routes read and write them. LB-9a's init and two owners' refreshes of
    the same scope run beside them; every #3514 table keeps its columns,
    constraints, indexes and rows exactly, and #3514's own store still works
    afterwards."""
    eid = _seed_3514(con)
    before = _snapshot_3514(con)
    for table in TABLES_3514:
        assert before[table][3], f"seed {table} so the check is live"  # type: ignore[index]

    init_companion_document_schema(con)
    init_companion_document_schema(con)
    replace_scope(con, _receipt("owner-a"), [_entry()])
    replace_scope(con, _receipt("owner-b"), [_entry()])

    assert _snapshot_3514(con) == before
    assert _primary_key(con, "evidence_index") == ["evidence_id"]
    assert _primary_key(con, "companion_document_evidence") == ["owner_user_id", "evidence_id"]
    assert [r[0] for r in _all_rows(con)] == ["owner-a", "owner-b"]
    # #3514's store is untouched and still serves its own rows.
    still = live_3514.resolve(con, eid)
    assert still is not None and still.owner_user_id == "owner-a"
    rows_3514 = live_3514.read_scope(
        con, owner_user_id="owner-a", scope="document", scope_id="doc-1"
    )
    assert [r.evidence_id for r in rows_3514] == [eid]


def test_3514_init_after_lb9a_init_leaves_lb9a_rows_alone(con: LockedConnection) -> None:
    """The other order: LB-9a's tables first, then #3514's init and rebuild
    (a #3514 route on first use). Both schemas stand; LB-9a's rows stay."""
    written = replace_scope(con, _receipt("owner-a"), [_entry()])
    _seed_3514(con)
    assert read_scope(con, owner_user_id="owner-a", scope="document", scope_id="doc-1") == written
    assert _primary_key(con, "companion_document_evidence") == ["owner_user_id", "evidence_id"]
    assert _primary_key(con, "evidence_index") == ["evidence_id"]


def test_init_refuses_a_companion_document_evidence_of_unknown_shape(
    con: LockedConnection,
) -> None:
    """A table under LB-9a's name that is not LB-9a's shape: refuse rather
    than write into it."""
    con.execute(
        "CREATE TABLE companion_document_evidence (evidence_id VARCHAR PRIMARY KEY, payload VARCHAR)"
    )
    with pytest.raises(RuntimeError, match="companion_document_evidence"):
        init_companion_document_schema(con)
    with pytest.raises(RuntimeError, match="companion_document_evidence"):
        replace_scope(con, _receipt("owner-a"), [_entry()])
    assert _primary_key(con, "companion_document_evidence") == ["evidence_id"]
    assert con.execute("SELECT COUNT(*) FROM companion_document_evidence").fetchone() == (0,)


def test_read_paths_see_nothing_before_init_and_never_read_3514(db: str) -> None:
    """A read connection never runs DDL: before any refresh the read helpers
    answer empty, and with #3514's table present and holding the very id
    asked for, LB-9a's reads still answer from LB-9a's table only."""
    with connect_write(db, purpose="test/lb9a-read", keepalive_s=0) as c:
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
    with connect_write(db, purpose="test/lb9a-read", keepalive_s=0) as c:
        eid = _seed_3514(c)
    reader = connect_read(db)
    try:
        assert read_scope(reader, owner_user_id="owner-a", scope="document", scope_id="doc-1") == ()
        assert resolve(reader, "owner-a", eid) is None
        assert not table_exists(reader, "companion_document_evidence")
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
