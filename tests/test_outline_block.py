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
from substrate.graph.ops import (
    attach_block_to_section,
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_node,
    insert_section,
    update_section_prose,
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
from substrate.write.provenance_validity import read_validity


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
        move_block(con, outline_block_id=obid, to_section_id=db["subsection"], to_index=2)
    con = _read(db["path"])
    moved = get_block(con, obid)
    con.close()
    assert moved.section_id == db["subsection"]
    assert moved.block_index == 2

    with connect_write(db["path"], purpose="t") as con:
        assert remove_block(con, outline_block_id=obid) is True
        assert remove_block(con, outline_block_id=obid) is False  # already gone
    con = _read(db["path"])
    assert get_block(con, obid) is None
    con.close()


def _ground_section(con, section_id, block_id):
    update_section_prose(
        con,
        section_id=section_id,
        prose_text="Grounded paragraph.",
        prose_provenance={"0": [block_id]},
    )


def _section_provenance(con, section_id):
    row = con.execute(
        "SELECT s.prose_text, s.prose_provenance, v.validity_json "
        "FROM deliverable_sections s LEFT JOIN "
        "deliverable_section_provenance_validity v ON v.section_id=s.section_id "
        "WHERE s.section_id=?",
        [section_id],
    ).fetchone()
    provenance = json.loads(row[1]) if row[1] else None
    return provenance, read_validity(row[0], provenance, row[2])


def test_structural_mutations_invalidate_current_provenance(db):
    with connect_write(db["path"], purpose="t") as con:
        first = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        _ground_section(con, db["section"], first)
        place_user_authored_block(
            con, section_id=db["section"], content="new input", block_index=1,
        )
        provenance, validity = _section_provenance(con, db["section"])
        assert provenance is None
        assert validity["paragraphs"]["0"]["status"] == "stale"
        assert validity["structural_reason"] == "block_placed"


def test_move_invalidates_source_and_destination(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        _ground_section(con, db["section"], obid)
        _ground_section(con, db["subsection"], "other-block")
        move_block(con, outline_block_id=obid, to_section_id=db["subsection"], to_index=2)
        for section_id in (db["section"], db["subsection"]):
            provenance, validity = _section_provenance(con, section_id)
            assert provenance is None
            assert validity["status"] == "stale"


def test_identical_move_preserves_validity(db):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        _ground_section(con, db["section"], obid)
        before = _section_provenance(con, db["section"])
        move_block(con, outline_block_id=obid, to_section_id=db["section"], to_index=0)
        assert _section_provenance(con, db["section"]) == before


@pytest.mark.parametrize("mutation", ["reorder", "remove"])
def test_reorder_and_remove_invalidate_referenced_provenance(db, mutation):
    with connect_write(db["path"], purpose="t") as con:
        obid = place_block(
            con, section_id=db["section"], block_kind="insight",
            provenance_kind="graph_node", node_id=db["node"], block_index=0,
        )
        _ground_section(con, db["section"], obid)
        if mutation == "reorder":
            move_block(con, outline_block_id=obid, to_section_id=db["section"], to_index=3)
        else:
            assert remove_block(con, outline_block_id=obid)
        provenance, validity = _section_provenance(con, db["section"])
        assert provenance is None
        assert validity["status"] == "stale"
        assert validity["structural_reason"] == f"block_{'moved' if mutation == 'reorder' else 'removed'}"


def test_cross_deliverable_move_is_rejected(db):
    with connect_write(db["path"], purpose="t") as con:
        other_did = insert_deliverable(con, title="Other", deliverable_kind="research_memo")
        other_section = insert_section(
            con, deliverable_id=other_did, section_index=0, title="Other"
        )
        obid = place_user_authored_block(
            con, section_id=db["section"], content="mine", block_index=0,
        )
        with pytest.raises(OutlineBlockError, match="across deliverables"):
            move_block(con, outline_block_id=obid, to_section_id=other_section, to_index=0)
        assert get_block(con, obid).section_id == db["section"]


def test_invalidation_failure_rolls_back_block_placement(db, monkeypatch):
    import substrate.write.outline_block as outline_module
    import substrate.write.provenance_validity as validity_module

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected invalidation failure")

    monkeypatch.setattr(validity_module, "invalidate_structural_provenance", fail)
    emitted = []
    monkeypatch.setattr(outline_module, "emit_typed", lambda *_args, **_kwargs: emitted.append(True))
    with connect_write(db["path"], purpose="t") as con:
        with pytest.raises(RuntimeError, match="injected"):
            place_user_authored_block(
                con, section_id=db["section"], content="must roll back", block_index=0,
            )
        assert list_section_blocks(con, db["section"]) == []
    assert emitted == []
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
