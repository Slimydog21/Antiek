"""Tests for the OutlineBlock composition layer (specs/write/ SPR-01).

Coverage maps to the sprint milestones + the rigor #3 edge cases:

M1 OutlineBlock model + taxonomy + the no-orphan-prose / no-fabricated-
   citation invariants (graph_node ⟺ node_id; user-originated ⟹ content).
M2 hierarchy/nesting — build the outline tree, deterministic ordering,
   reparent with cycle detection.
M3 provenance resolution — resolved (node→chunk→doc), dangling (node
   deleted), user_originated (no fabricated source).
M4 clustering — shared-document grouping, deterministic.
M5 single-writer (LockedConnection required) + typed events emitted +
   the new action types are in the typed union.
M6 migration — section_blocks → outline_blocks, idempotent, lossless;
   existing deliverables still load.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.graph.ops import (
    attach_block_to_section,
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_node,
    insert_section,
)
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import TYPED_PAYLOAD_ACTION_TYPES
from substrate.write import (
    OutlineBlockError,
    get_block,
    list_section_blocks,
    move_block,
    place_block,
    place_user_authored_block,
    remove_block,
)
from substrate.write.clustering import cluster_blocks
from substrate.write.migrate_outline_block import migrate
from substrate.write.outline import (
    OutlineError,
    build_outline_tree,
    flatten_outline,
    reparent_section,
)
from substrate.write.provenance import resolve_provenance


@pytest.fixture()
def db(monkeypatch):
    """A temp DB with a deliverable, a nested section skeleton, and a
    document→chunk→node provenance chain. Events go to a temp dir."""
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    path = os.path.join(d, "antiek.duckdb")
    init_database_at_path(path)

    with connect_write(path, purpose="test/seed") as con:
        did = insert_deliverable(con, title="Test memo", deliverable_kind="research_memo")
        # Hierarchy: chapter → section → subsection
        chapter = insert_section(con, deliverable_id=did, section_index=0, title="Chapter 1")
        section = insert_section(
            con, deliverable_id=did, section_index=0, title="Section 1.1",
            parent_section_id=chapter,
        )
        subsection = insert_section(
            con, deliverable_id=did, section_index=0, title="Subsection 1.1.1",
            parent_section_id=section,
        )
        # Provenance chain: document → chunk → node (node.metadata.chunk_id).
        doc = insert_document(
            con, document_id="doc-1", source_tier=2, document_type="paper",
            title="A Source Paper",
        )
        chunk = insert_chunk(con, document_id=doc, chunk_index=0, text="some evidence text")
        node = insert_node(
            con, canonical_label="an insight about X", node_type="claim",
            graph_scope="cross_domain", investigation_id="__operator__",
            metadata={"chunk_id": chunk},
        )
    return {
        "path": path, "deliverable_id": did, "chapter": chapter,
        "section": section, "subsection": subsection,
        "node": node, "chunk": chunk, "document": doc,
    }


def _read(path):
    return duckdb.connect(path, read_only=True)


# ── M1 — model + invariants ────────────────────────────────────────


def test_place_graph_node_block(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
    con = _read(db["path"])
    block = get_block(con, obid)
    con.close()
    assert block is not None
    assert block.node_id == db["node"]
    assert block.provenance_kind == "graph_node"
    assert block.content is None
    assert not block.is_user_originated


def test_place_user_authored_block(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_user_authored_block(
            con, section_id=db["section"], content="my own thought", block_index=1,
        )
    con = _read(db["path"])
    block = get_block(con, obid)
    con.close()
    assert block.is_user_originated
    assert block.node_id is None
    assert block.content == "my own thought"


def test_event_filesystem_failure_leaves_pending_intent(db, monkeypatch):
    import substrate.write.event_outbox as outbox_module

    monkeypatch.setattr(
        outbox_module,
        "investigation_event_lock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with connect_write(db["path"], purpose="t") as con:
        obid = place_user_authored_block(
            con,
            section_id=db["section"],
            content="durable while event storage is unavailable",
            block_index=0,
        )
        assert get_block(con, obid) is not None
        assert con.execute(
            "SELECT state FROM write_event_outbox WHERE aggregate_id=?",
            [obid],
        ).fetchone() == ("pending",)


def test_graph_node_block_requires_node_id(db):
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineBlockError, match="no-orphan-prose"):
            place_block(
                con, section_id=db["section"], block_kind="insight",
                provenance_kind="graph_node", node_id=None, block_index=0,
            )


def test_user_originated_block_rejects_node_id(db):
    """A user-originated block with a node_id would fabricate a citation."""
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineBlockError, match="fabricates a citation"):
            place_block(
                con, section_id=db["section"], block_kind="user_authored",
                provenance_kind="user_authored", node_id=db["node"],
                content="x", block_index=0,
            )


def test_incoherent_kind_pair_rejected(db):
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineBlockError, match="incoherent"):
            place_block(
                con, section_id=db["section"], block_kind="claim",
                provenance_kind="user_authored", content="x", block_index=0,
            )


def test_node_backed_block_rejects_inline_content(db):
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineBlockError, match="must not carry inline content"):
            place_block(
                con, section_id=db["section"], block_kind="insight",
                provenance_kind="graph_node", node_id=db["node"],
                content="should not be here", block_index=0,
            )


def test_db_check_enforces_invariant_independently(db):
    """Belt-and-suspenders: even a raw INSERT bypassing the app layer is
    rejected by the DB CHECK (graph_node ⟹ node_id present)."""
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO outline_blocks "
                "(outline_block_id, section_id, block_kind, provenance_kind, "
                " node_id, block_index) VALUES (?, ?, ?, ?, ?, ?)",
                ["oblk-raw", db["section"], "insight", "graph_node", None, 0],
            )


# ── M2 — hierarchy ─────────────────────────────────────────────────


def test_build_outline_tree_nesting(db):
    con = _read(db["path"])
    roots = build_outline_tree(con, db["deliverable_id"])
    con.close()
    assert len(roots) == 1
    chapter = roots[0]
    assert chapter.section_id == db["chapter"]
    assert chapter.depth == 0
    assert len(chapter.children) == 1
    section = chapter.children[0]
    assert section.depth == 1
    assert section.children[0].section_id == db["subsection"]
    assert section.children[0].depth == 2


def test_reparent_with_cycle_detection(db):
    # Reparent chapter under its own descendant (subsection) → cycle.
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineError, match="cycle"):
            reparent_section(
                con, section_id=db["chapter"],
                new_parent_section_id=db["subsection"],
            )
    # A legal reparent (subsection → chapter directly) works.
    with connect_write(db["path"], purpose="t") as con:
        reparent_section(
            con, section_id=db["subsection"],
            new_parent_section_id=db["chapter"],
        )
    con = _read(db["path"])
    roots = build_outline_tree(con, db["deliverable_id"])
    con.close()
    chapter = roots[0]
    child_ids = {c.section_id for c in chapter.children}
    assert db["subsection"] in child_ids  # now a direct child of chapter


def test_section_cannot_be_own_parent(db):
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(OutlineError, match="own parent"):
            reparent_section(
                con, section_id=db["chapter"], new_parent_section_id=db["chapter"],
            )


def test_flatten_outline_preorder(db):
    con = _read(db["path"])
    roots = build_outline_tree(con, db["deliverable_id"])
    con.close()
    flat = flatten_outline(roots)
    ids = [n.section_id for n in flat]
    assert ids == [db["chapter"], db["section"], db["subsection"]]


# ── M3 — provenance resolution ─────────────────────────────────────


def test_provenance_resolved(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
    con = _read(db["path"])
    chain = resolve_provenance(con, obid)
    con.close()
    assert chain.status == "resolved"
    assert chain.node_id == db["node"]
    assert chain.document_id == db["document"]
    assert db["chunk"] in chain.chunk_ids
    assert chain.has_source_document


def test_provenance_dangling(db):
    """A block whose source node is deleted surfaces as dangling, not a
    crash (rigor #3)."""
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id="node-gone", block_index=0,
        )
    con = _read(db["path"])
    chain = resolve_provenance(con, obid)
    con.close()
    assert chain.status == "dangling"
    assert "unavailable" in chain.detail


def test_provenance_user_originated(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_user_authored_block(
            con, section_id=db["section"], content="mine", block_index=0,
        )
    con = _read(db["path"])
    chain = resolve_provenance(con, obid)
    con.close()
    assert chain.status == "user_originated"
    assert chain.document_id is None
    assert not chain.has_source_document


# ── M4 — clustering ────────────────────────────────────────────────


def test_clustering_shared_document_is_deterministic(db):
    # Two nodes from the same document → two blocks that cluster together.
    with connect_write(db["path"], purpose="t") as con:
        node2 = insert_node(
            con, canonical_label="another insight", node_type="claim",
            graph_scope="cross_domain", investigation_id="__operator__",
            metadata={"chunk_id": db["chunk"]},
        )
        b1 = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        b2 = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=node2, block_index=1,
        )
    con = _read(db["path"])
    clusters_a = cluster_blocks(con, db["section"])
    clusters_b = cluster_blocks(con, db["section"])
    con.close()
    # Determinism: same input → identical cluster ids + membership.
    assert list(clusters_a.keys()) == list(clusters_b.keys())
    doc_cluster = clusters_a[f"doc:{db['document']}"]
    member_ids = {b.outline_block_id for b in doc_cluster}
    assert member_ids == {b1, b2}


# ── M5 — single-writer + events ────────────────────────────────────


def test_write_requires_locked_connection(db):
    raw = duckdb.connect(db["path"])
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            place_block(
                raw, section_id=db["section"], block_kind="insight",
                provenance_kind="graph_node", node_id=db["node"], block_index=0,
            )
    finally:
        raw.close()


def test_placed_event_emitted(db, monkeypatch):
    events_dir = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]
    with connect_write(db["path"], purpose="t") as con:
        place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
            investigation_id="__operator__",
        )
    jsonl = os.path.join(events_dir, "__operator__.jsonl")
    assert os.path.exists(jsonl)
    actions = [json.loads(line)["action_type"] for line in open(jsonl)]
    assert "outline_block.placed" in actions


def test_new_action_types_in_typed_union():
    for at in ("outline_block.placed", "outline_block.moved", "outline_block.removed"):
        assert at in TYPED_PAYLOAD_ACTION_TYPES


def test_move_and_remove(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(con, outline_block_id=obid, to_section_id=db["subsection"], to_index=2)
    con = _read(db["path"])
    moved = get_block(con, obid)
    con.close()
    assert moved.section_id == db["subsection"]
    assert moved.block_index == 0

    with connect_write(db["path"], purpose="t") as con:
        assert remove_block(con, outline_block_id=obid) is True
        assert remove_block(con, outline_block_id=obid) is False  # already gone
    con = _read(db["path"])
    assert get_block(con, obid) is None
    con.close()


@pytest.fixture()
def ordering_db(tmp_path, monkeypatch):
    source = Path(_REPO, "README.md").read_bytes()
    paragraphs = [p.strip() for p in source.decode().split("\n\n") if p.strip()][:4]
    path = str(tmp_path / "ordering.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    with connect_write(path, purpose="outline/order-regression") as con:
        did = insert_deliverable(
            con,
            title=paragraphs[0].removeprefix("# "),
            deliverable_kind="research_memo",
        )
        sections = [
            insert_section(con, deliverable_id=did, section_index=i, title=None) for i in range(2)
        ]
        blocks = [
            place_user_authored_block(
                con,
                section_id=sections[0],
                content=text,
                block_index=i,
                metadata={
                    "repository_source": "README.md",
                    "sha256": hashlib.sha256(source).hexdigest(),
                },
            )
            for i, text in enumerate(paragraphs)
        ]
    return path, sections, blocks


@pytest.mark.parametrize(
    "source_index,target_index,final_index",
    [(1, 0, 0), (0, 3, 3), (3, 1, 1), (2, 3, 3), (1, -1, 0)],
)
def test_ordering_move_uses_final_position(ordering_db, source_index, target_index, final_index):
    path, sections, ids = ordering_db
    expected = ids.copy()
    expected.insert(final_index, expected.pop(source_index))
    with connect_write(path, purpose="outline/order-regression") as con:
        before = {b.outline_block_id: b for b in list_section_blocks(con, sections[0])}
        move_block(
            con,
            outline_block_id=ids[source_index],
            to_section_id=sections[0],
            to_index=target_index,
        )
        after = list_section_blocks(con, sections[0])
        assert [b.outline_block_id for b in after] == expected
        assert [b.block_index for b in after] == list(range(len(ids)))
        for b in after:
            assert b.content == before[b.outline_block_id].content
            assert b.metadata == before[b.outline_block_id].metadata
            assert b.node_id == before[b.outline_block_id].node_id
            assert b.provenance_kind == before[b.outline_block_id].provenance_kind


@pytest.mark.parametrize("ranks", [(0, 0, 5, 12), (4, 7, 20, 31)])
def test_ordering_repairs_duplicate_and_sparse_ranks(ordering_db, ranks):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        for block_id, rank in zip(ids, ranks, strict=True):
            con.execute(
                "UPDATE outline_blocks SET block_index=? WHERE outline_block_id=?", [rank, block_id]
            )
        original = list_section_blocks(con, sections[0])
        from_rank = original[1].block_index
        before = [b.outline_block_id for b in original]
        moved = before.pop(1)
        before.insert(0, moved)
        move_block(con, outline_block_id=moved, to_section_id=sections[0], to_index=0)
        after = list_section_blocks(con, sections[0])
        assert [b.outline_block_id for b in after] == before
        assert [b.block_index for b in after] == list(range(len(ids)))
        event = json.loads(
            con.execute(
                "SELECT event_json FROM write_event_outbox WHERE aggregate_id=? "
                "AND operation_id LIKE 'outline.move:%'",
                [moved],
            ).fetchone()[0]
        )
        assert event["payload"]["from_index"] == from_rank
        assert event["payload"]["to_index"] == 0


def test_ordering_same_position_repairs_legacy_ranks(ordering_db):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        con.execute("UPDATE outline_blocks SET block_index=0 WHERE section_id=?", [sections[0]])
        before = [b.outline_block_id for b in list_section_blocks(con, sections[0])]
        move_block(con, outline_block_id=before[0], to_section_id=sections[0], to_index=0)
        after = list_section_blocks(con, sections[0])
        assert [b.outline_block_id for b in after] == before
        assert [b.block_index for b in after] == list(range(len(ids)))


def test_ordering_cross_section_clamps_and_records_effective_position(ordering_db):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        move_block(con, outline_block_id=ids[1], to_section_id=sections[1], to_index=99)
        assert [b.block_index for b in list_section_blocks(con, sections[0])] == [0, 1, 2]
        assert [
            (b.outline_block_id, b.block_index) for b in list_section_blocks(con, sections[1])
        ] == [(ids[1], 0)]
        event = json.loads(
            con.execute(
                "SELECT event_json FROM write_event_outbox WHERE aggregate_id=? AND operation_id LIKE 'outline.move:%'",
                [ids[1]],
            ).fetchone()[0]
        )
        assert event["payload"]["from_index"] == 1
        assert event["payload"]["to_index"] == 0


@pytest.mark.parametrize("target_index", [0, 99])
def test_ordering_cross_section_preserves_populated_destination(ordering_db, target_index):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        move_block(con, outline_block_id=ids[0], to_section_id=sections[1], to_index=0)
        move_block(con, outline_block_id=ids[1], to_section_id=sections[1], to_index=target_index)
        destination = [ids[1], ids[0]] if target_index == 0 else [ids[0], ids[1]]
        assert [b.outline_block_id for b in list_section_blocks(con, sections[0])] == ids[2:]
        assert [b.block_index for b in list_section_blocks(con, sections[0])] == [0, 1]
        assert [b.outline_block_id for b in list_section_blocks(con, sections[1])] == destination
        assert [b.block_index for b in list_section_blocks(con, sections[1])] == [0, 1]


def test_ordering_failure_rolls_back_all_ranks_and_receipt(ordering_db, monkeypatch):
    import substrate.write.event_outbox as outbox

    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        before = con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
        receipts = con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall()

        def fail_enqueue(*args, **kwargs):
            raise RuntimeError("injected outbox failure")

        monkeypatch.setattr(outbox, "enqueue_event", fail_enqueue)
        with pytest.raises(RuntimeError, match="injected outbox failure"):
            move_block(con, outline_block_id=ids[1], to_section_id=sections[0], to_index=0)
        assert (
            con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
            == before
        )
        assert (
            con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall() == receipts
        )


def test_ordering_dense_same_position_does_not_add_receipt(ordering_db):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        before = con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
        receipts = con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall()
        move_block(con, outline_block_id=ids[1], to_section_id=sections[0], to_index=1)
        assert (
            con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
            == before
        )
        assert (
            con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall() == receipts
        )


def test_ordering_dense_noop_delivers_pending_move(ordering_db, monkeypatch, tmp_path):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
        move_block(con, outline_block_id=ids[1], to_section_id=sections[0], to_index=0)
        pending = con.execute(
            "SELECT event_id, state FROM write_event_outbox "
            "WHERE operation_id LIKE 'outline.move:%'"
        ).fetchall()
        assert len(pending) == 1 and pending[0][1] == "pending"
        event_log = tmp_path / "events" / "__operator__.jsonl"
        assert pending[0][0] not in event_log.read_text()
        monkeypatch.delenv("ANTIEK_EVENTS_DISABLED")
        move_block(con, outline_block_id=ids[1], to_section_id=sections[0], to_index=0)
        assert con.execute(
            "SELECT event_id, state FROM write_event_outbox "
            "WHERE operation_id LIKE 'outline.move:%'"
        ).fetchall() == [(pending[0][0], "delivered")]
        assert [b.outline_block_id for b in list_section_blocks(con, sections[0])] == [
            ids[1],
            ids[0],
            ids[2],
            ids[3],
        ]
        emitted = [json.loads(line)["event_id"] for line in event_log.read_text().splitlines()]
        assert emitted.count(pending[0][0]) == 1


def test_ordering_invalid_target_is_atomic(ordering_db):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        before = con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
        receipts = con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall()
        with pytest.raises(OutlineBlockError, match="target section not found"):
            move_block(con, outline_block_id=ids[1], to_section_id="", to_index=0)
        assert (
            con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
            == before
        )
        assert (
            con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall() == receipts
        )


def test_ordering_outer_transaction_retains_rollback_authority(ordering_db, tmp_path):
    path, sections, ids = ordering_db
    with connect_write(path, purpose="outline/order-regression") as con:
        before = con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
        receipts = con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall()
        event_log = tmp_path / "events" / "__operator__.jsonl"
        emitted = event_log.read_bytes()
        with pytest.raises(RuntimeError, match="outer operation aborted"), con.transaction():
            move_block(con, outline_block_id=ids[1], to_section_id=sections[0], to_index=0)
            assert [b.outline_block_id for b in list_section_blocks(con, sections[0])] == [
                ids[1],
                ids[0],
                ids[2],
                ids[3],
            ]
            assert event_log.read_bytes() == emitted
            raise RuntimeError("outer operation aborted")
        assert (
            con.execute("SELECT * FROM outline_blocks ORDER BY outline_block_id").fetchall()
            == before
        )
        assert (
            con.execute("SELECT * FROM write_event_outbox ORDER BY event_id").fetchall() == receipts
        )
        assert event_log.read_bytes() == emitted


# ── M6 — migration ─────────────────────────────────────────────────


def test_migration_lossless_and_idempotent(db):
    # Seed legacy section_blocks rows.
    with connect_write(db["path"], purpose="t") as con:
        attach_block_to_section(
            con, section_id=db["section"], block_kind="insight",
            block_id=db["node"], block_index=0,
        )
        attach_block_to_section(
            con, section_id=db["section"], block_kind="operator_note",
            block_id="note-123", block_index=1,
        )

    with connect_write(db["path"], purpose="t") as con:
        result1 = migrate(con)
    assert result1.migrated == 2
    assert result1.skipped == 0

    con = _read(db["path"])
    blocks = list_section_blocks(con, db["section"])
    con.close()
    by_kind = {b.block_kind: b for b in blocks}
    # insight migrated as graph_node with node_id == original block_id.
    assert by_kind["insight"].provenance_kind == "graph_node"
    assert by_kind["insight"].node_id == db["node"]
    assert by_kind["insight"].source_block_id == db["node"]
    # operator_note migrated as user_authored, no fabricated node.
    assert by_kind["operator_note"].provenance_kind == "user_authored"
    assert by_kind["operator_note"].node_id is None

    # Idempotent: a second run is a pure no-op (all skipped).
    with connect_write(db["path"], purpose="t") as con:
        result2 = migrate(con)
    assert result2.migrated == 0
    assert result2.skipped == 2

    # Existing deliverable still loads after migration.
    con = _read(db["path"])
    roots = build_outline_tree(con, db["deliverable_id"])
    con.close()
    assert len(roots) == 1
