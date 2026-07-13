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

import json
import os
import sys
import tempfile

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.event_log import trajectory
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
    OutlineBlockCommandConflict,
    OutlineBlockError,
    get_block,
    list_section_blocks,
    move_block,
    place_block,
    place_user_authored_block,
    remove_block,
)
from substrate.write import outline_block as outline_block_mod
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
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="move-basic",
        )
    con = _read(db["path"])
    moved = get_block(con, obid)
    con.close()
    assert moved.section_id == db["subsection"]
    assert moved.block_index == 2

    with connect_write(db["path"], purpose="t") as con:
        assert remove_block(
            con, outline_block_id=obid, command_id="remove-basic",
        ) is True
        assert remove_block(
            con, outline_block_id=obid, command_id="remove-basic",
        ) is True
        assert remove_block(
            con, outline_block_id=obid, command_id="remove-new-intent",
        ) is False
    con = _read(db["path"])
    assert get_block(con, obid) is None
    con.close()


def test_move_replay_repairs_event_without_rewinding_later_state(db, monkeypatch):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        original_append = outline_block_mod.append_event_once
        monkeypatch.setattr(
            outline_block_mod,
            "append_event_once",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(OSError, match="disk full"):
            move_block(
                con,
                outline_block_id=obid,
                to_section_id=db["subsection"],
                to_index=2,
                command_id="move-repair",
            )

        monkeypatch.setattr(outline_block_mod, "append_event_once", original_append)
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["section"],
            to_index=4,
            command_id="move-later",
        )
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="move-repair",
        )

    con = _read(db["path"])
    try:
        block = get_block(con, obid)
        assert (block.section_id, block.block_index) == (db["section"], 4)
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands"
        ).fetchone()[0] == 2
    finally:
        con.close()
    repaired = [
        row for row in trajectory("__operator__")
        if row["action_type"] == "outline_block.moved"
        and row["payload"]["to_index"] == 2
    ]
    assert len(repaired) == 1
    assert repaired[0]["payload"] == {
        "action_type": "outline_block.moved",
        "outline_block_id": obid,
        "from_section_id": db["section"],
        "to_section_id": db["subsection"],
        "from_index": 0,
        "to_index": 2,
    }


def test_remove_replay_repairs_event_and_remains_successful(db, monkeypatch):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        original_append = outline_block_mod.append_event_once
        monkeypatch.setattr(
            outline_block_mod,
            "append_event_once",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )
        with pytest.raises(OSError, match="disk full"):
            remove_block(con, outline_block_id=obid, command_id="remove-repair")
        assert get_block(con, obid) is None

        monkeypatch.setattr(outline_block_mod, "append_event_once", original_append)
        assert remove_block(
            con, outline_block_id=obid, command_id="remove-repair",
        ) is True

    removed = [
        row for row in trajectory("__operator__")
        if row["action_type"] == "outline_block.removed"
    ]
    assert len(removed) == 1
    assert removed[0]["payload"]["section_id"] == db["section"]


def test_command_id_conflict_never_mutates_current_state(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="immutable-command",
        )
        with pytest.raises(OutlineBlockCommandConflict):
            move_block(
                con,
                outline_block_id=obid,
                to_section_id=db["section"],
                to_index=3,
                command_id="immutable-command",
            )
        block = get_block(con, obid)
        assert (block.section_id, block.block_index) == (db["subsection"], 2)


@pytest.mark.parametrize("changed_material", ["operation", "block", "investigation", "parent"])
def test_command_fingerprint_rejects_every_identity_dimension(db, changed_material):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="all-material",
            parent_event_id="parent-1",
        )
        with pytest.raises(OutlineBlockCommandConflict):
            if changed_material == "operation":
                remove_block(
                    con,
                    outline_block_id=obid,
                    command_id="all-material",
                    parent_event_id="parent-1",
                )
            elif changed_material == "block":
                other = place_block(
                    con, section_id=db["section"], block_kind="insight",
                    provenance_kind="graph_node", node_id=db["node"], block_index=4,
                )
                move_block(
                    con,
                    outline_block_id=other,
                    to_section_id=db["subsection"],
                    to_index=2,
                    command_id="all-material",
                    parent_event_id="parent-1",
                )
            elif changed_material == "investigation":
                move_block(
                    con,
                    outline_block_id=obid,
                    to_section_id=db["subsection"],
                    to_index=2,
                    command_id="all-material",
                    investigation_id="other-investigation",
                    parent_event_id="parent-1",
                )
            else:
                move_block(
                    con,
                    outline_block_id=obid,
                    to_section_id=db["subsection"],
                    to_index=2,
                    command_id="all-material",
                    parent_event_id="parent-2",
                )


def test_distinct_commands_can_reuse_an_earlier_destination(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        destinations = [
            (db["subsection"], 2, "move-out"),
            (db["section"], 0, "move-back"),
            (db["subsection"], 2, "move-out-again"),
        ]
        for section_id, index, command_id in destinations:
            move_block(
                con,
                outline_block_id=obid,
                to_section_id=section_id,
                to_index=index,
                command_id=command_id,
            )
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands WHERE operation = 'move'"
        ).fetchone()[0] == 3
    moved = [
        row for row in trajectory("__operator__")
        if row["action_type"] == "outline_block.moved"
    ]
    assert len(moved) == 3


def test_move_replay_after_deletion_never_resurrects_block(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="move-before-delete",
        )
        assert remove_block(
            con, outline_block_id=obid, command_id="delete-after-move",
        ) is True
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=2,
            command_id="move-before-delete",
        )
        assert get_block(con, obid) is None


def test_command_insert_failure_rolls_back_move(db, monkeypatch):
    with connect_write(db["path"], purpose="t") as con:
        first = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(
            con,
            outline_block_id=first,
            to_section_id=db["subsection"],
            to_index=1,
            command_id="event-owner",
        )
        event_id = con.execute(
            "SELECT event_id FROM outline_block_commands WHERE command_id = ?",
            ["event-owner"],
        ).fetchone()[0]
        second = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=3,
        )
        monkeypatch.setattr(
            outline_block_mod, "_command_event_id", lambda _command_id: event_id,
        )
        with pytest.raises(duckdb.ConstraintException):
            move_block(
                con,
                outline_block_id=second,
                to_section_id=db["subsection"],
                to_index=4,
                command_id="event-collision",
            )
        block = get_block(con, second)
        assert (block.section_id, block.block_index) == (db["section"], 3)
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands WHERE command_id = ?",
            ["event-collision"],
        ).fetchone()[0] == 0


def test_command_insert_failure_rolls_back_remove(db, monkeypatch):
    with connect_write(db["path"], purpose="t") as con:
        first = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        assert remove_block(
            con, outline_block_id=first, command_id="remove-event-owner",
        ) is True
        event_id = con.execute(
            "SELECT event_id FROM outline_block_commands WHERE command_id = ?",
            ["remove-event-owner"],
        ).fetchone()[0]
        second = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=3,
        )
        monkeypatch.setattr(
            outline_block_mod, "_command_event_id", lambda _command_id: event_id,
        )
        with pytest.raises(duckdb.ConstraintException):
            remove_block(
                con, outline_block_id=second, command_id="remove-event-collision",
            )
        assert get_block(con, second) is not None
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands WHERE command_id = ?",
            ["remove-event-collision"],
        ).fetchone()[0] == 0


@pytest.mark.parametrize("operation", ["move", "remove"])
def test_disabled_event_store_rejects_before_mutation(db, monkeypatch, operation):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
        with pytest.raises(RuntimeError, match="event persistence is disabled"):
            if operation == "move":
                move_block(
                    con,
                    outline_block_id=obid,
                    to_section_id=db["subsection"],
                    to_index=2,
                    command_id="disabled-move",
                )
            else:
                remove_block(
                    con, outline_block_id=obid, command_id="disabled-remove",
                )
        block = get_block(con, obid)
        assert (block.section_id, block.block_index) == (db["section"], 0)
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands"
        ).fetchone()[0] == 0


def test_existing_database_lazily_receives_command_table(db):
    with connect_write(db["path"], purpose="t") as con:
        con.execute("DROP TABLE outline_block_commands")
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        move_block(
            con,
            outline_block_id=obid,
            to_section_id=db["subsection"],
            to_index=1,
            command_id="lazy-schema",
        )
        assert con.execute(
            "SELECT COUNT(*) FROM outline_block_commands"
        ).fetchone()[0] == 1


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
