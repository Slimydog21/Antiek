"""Tests for the block repository + folders (specs/write/ SPR-03, backend).

M1 folders — group blocks across investigations as views/edges over
   nodes; a block in two folders is ONE underlying node (no copies).
M2 search — ranked + deterministic; text + folder + source filters.
M4 provenance preserved — a folder membership is a node reference; the
   provenance chain (block→node→document) still resolves.
M5 single-writer — folder writes require a LockedConnection.

(The drag-into-outline UI and Storybook are frontend — out of scope for
this backend slice; the drag creates an OutlineBlock referencing the same
node, which is the SPR-01 place_block path, already tested.)
"""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document, insert_node
from substrate.graph.schema import init_database_at_path
from substrate.write.block_search import search_blocks
from substrate.write.folders import (
    add_block_to_folder,
    create_folder,
    ensure_folders_schema,
    folders_for_node,
    list_folder_node_ids,
    list_folders,
    remove_block_from_folder,
)
from substrate.write.provenance import resolve_provenance


@pytest.fixture()
def db(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    path = os.path.join(d, "antiek.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="test/seed") as con:
        ensure_folders_schema(con)
        # Two investigations, two documents, three nodes.
        doc1 = insert_document(con, document_id="doc-A", source_tier=2,
                               document_type="paper", title="Paper A")
        doc2 = insert_document(con, document_id="doc-B", source_tier=3,
                               document_type="paper", title="Paper B")
        ch1 = insert_chunk(con, document_id=doc1, chunk_index=0, text="capital intensity rises")
        ch2 = insert_chunk(con, document_id=doc2, chunk_index=0, text="provenance is the moat")
        n1 = insert_node(con, canonical_label="capital intensity rises with scale",
                         node_type="claim", graph_scope="cross_domain",
                         investigation_id="inv-1", metadata={"chunk_id": ch1})
        n2 = insert_node(con, canonical_label="provenance is the moat",
                         node_type="claim", graph_scope="cross_domain",
                         investigation_id="inv-2", metadata={"chunk_id": ch2})
        n3 = insert_node(con, canonical_label="the edit is the writing",
                         node_type="claim", graph_scope="cross_domain",
                         investigation_id="inv-2", metadata={"chunk_id": ch2})
    return {"path": path, "n1": n1, "n2": n2, "n3": n3, "doc1": doc1, "doc2": doc2}


def _read(path):
    return duckdb.connect(path, read_only=True)


# ── M1 — folders as views over nodes ───────────────────────────────


def test_folder_spans_investigations(db):
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="cross-inv folder")
        add_block_to_folder(con, folder_id=fid, node_id=db["n1"])  # inv-1
        add_block_to_folder(con, folder_id=fid, node_id=db["n2"])  # inv-2
    con = _read(db["path"])
    members = list_folder_node_ids(con, fid)
    con.close()
    assert set(members) == {db["n1"], db["n2"]}  # spans investigations


def test_block_in_two_folders_is_one_node(db):
    """The load-bearing invariant: multi-membership references ONE node,
    never a copy."""
    with connect_write(db["path"], purpose="t") as con:
        f1 = create_folder(con, name="folder one")
        f2 = create_folder(con, name="folder two")
        add_block_to_folder(con, folder_id=f1, node_id=db["n1"])
        add_block_to_folder(con, folder_id=f2, node_id=db["n1"])
    con = _read(db["path"])
    fids = folders_for_node(con, db["n1"])
    # One underlying node row, referenced by two folders.
    node_count = con.execute("SELECT COUNT(*) FROM nodes WHERE node_id = ?", [db["n1"]]).fetchone()[0]
    con.close()
    assert set(fids) == {f1, f2}
    assert node_count == 1  # not duplicated into folders


def test_add_block_is_idempotent(db):
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="f")
        assert add_block_to_folder(con, folder_id=fid, node_id=db["n1"]) is True
        assert add_block_to_folder(con, folder_id=fid, node_id=db["n1"]) is False
    con = _read(db["path"])
    assert list_folder_node_ids(con, fid) == [db["n1"]]
    con.close()


def test_remove_block_leaves_node_intact(db):
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="f")
        add_block_to_folder(con, folder_id=fid, node_id=db["n1"])
        assert remove_block_from_folder(con, folder_id=fid, node_id=db["n1"]) is True
    con = _read(db["path"])
    assert list_folder_node_ids(con, fid) == []
    # Node untouched — folder is a view.
    assert con.execute("SELECT COUNT(*) FROM nodes WHERE node_id = ?", [db["n1"]]).fetchone()[0] == 1
    con.close()


# ── M2 — search ranking ────────────────────────────────────────────


def test_search_ranks_and_is_deterministic(db):
    con = _read(db["path"])
    a = search_blocks(con, query="provenance moat", limit=10)
    b = search_blocks(con, query="provenance moat", limit=10)
    con.close()
    # Same query → identical ordering (determinism).
    assert [h.node_id for h in a] == [h.node_id for h in b]
    # The matching node ranks first.
    assert a[0].node_id == db["n2"]
    assert a[0].score > 0


def test_search_folder_filter(db):
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="only-n3")
        add_block_to_folder(con, folder_id=fid, node_id=db["n3"])
    con = _read(db["path"])
    hits = search_blocks(con, query="", folder_id=fid, limit=10)
    con.close()
    assert {h.node_id for h in hits} == {db["n3"]}


def test_search_source_document_filter(db):
    con = _read(db["path"])
    hits = search_blocks(con, query="", source_document_id=db["doc2"], limit=10)
    con.close()
    # doc-B sourced both n2 and n3.
    assert {h.node_id for h in hits} == {db["n2"], db["n3"]}


def test_search_resolves_source_title(db):
    con = _read(db["path"])
    hits = search_blocks(con, query="capital intensity", limit=10)
    con.close()
    top = hits[0]
    assert top.node_id == db["n1"]
    assert top.document_title == "Paper A"
    assert top.source_tier == 2


# ── M4 — provenance preserved through the repository ───────────────


def test_folder_membership_preserves_provenance(db):
    """A folder membership is a node reference, so the provenance chain
    still resolves (block→node→document)."""
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="f")
        add_block_to_folder(con, folder_id=fid, node_id=db["n1"])
    con = _read(db["path"])
    # Resolve provenance directly off the node a folder references.
    from substrate.write.outline_block import OutlineBlock
    pseudo = OutlineBlock(
        outline_block_id="probe", section_id="-", block_kind="claim",
        provenance_kind="graph_node", node_id=db["n1"], source_block_kind=None,
        source_block_id=None, content=None, block_index=0, cluster_id=None,
    )
    chain = resolve_provenance(con, pseudo)
    con.close()
    assert chain.status == "resolved"
    assert chain.document_id == db["doc1"]


# ── M5 — single-writer ─────────────────────────────────────────────


def test_folder_write_requires_locked_connection(db):
    raw = duckdb.connect(db["path"])
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            create_folder(raw, name="nope")
    finally:
        raw.close()


def test_list_folders_reports_member_counts(db):
    with connect_write(db["path"], purpose="t") as con:
        fid = create_folder(con, name="counted")
        add_block_to_folder(con, folder_id=fid, node_id=db["n1"])
        add_block_to_folder(con, folder_id=fid, node_id=db["n2"])
    con = _read(db["path"])
    folders = {f.folder_id: f for f in list_folders(con)}
    con.close()
    assert folders[fid].member_count == 2
