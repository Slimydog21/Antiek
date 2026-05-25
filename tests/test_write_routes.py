"""Tests for the Write REST surface (specs/write/, interfaces/research/api/write_routes.py).

Exercises the router end-to-end via TestClient against a temp DB:
  • outline composition (place / move / remove / outline tree) — SPR-01
  • provenance + trace target, incl. the gated-source-no-leak gate — SPR-01/07
  • folders (views over nodes) + search — SPR-03
  • brainstorm → user-originated blocks — SPR-05
  • context promote — SPR-08
  • generation: the no-blocks→gap path (no model needed) — SPR-06

The live generation path (a real model call) needs creative_writer wired
into the dispatch config + credentials; that path returns 503 here rather
than fabricating prose, and is not asserted.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import create_app
from runtime.db_lock import connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import (
    insert_chunk, insert_deliverable, insert_document, insert_node, insert_section,
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point the app + substrate at a temp DB + events dir."""
    db = str(tmp_path / "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(default_db_path())
    return db


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def seed():
    """A deliverable + section + a document→chunk→node provenance chain."""
    with connect_write(default_db_path(), purpose="test/seed") as con:
        did = insert_deliverable(con, title="Memo", deliverable_kind="research_memo")
        sec = insert_section(con, deliverable_id=did, section_index=0, title="S1")
        doc = insert_document(con, document_id="doc-1", source_tier=2,
                              document_type="book", title="Source Book")
        con.execute("UPDATE documents SET content_class='public_domain' WHERE document_id=?", [doc])
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="a sourced insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
        gated_doc = insert_document(con, document_id="doc-gated", source_tier=2,
                                    document_type="book", title="Gated Book")
        con.execute("UPDATE documents SET content_class='restricted_pending_opt_in' "
                    "WHERE document_id=?", [gated_doc])
        gch = insert_chunk(con, document_id=gated_doc, chunk_index=0, text="gated passage")
        gnode = insert_node(con, canonical_label="a gated insight", node_type="claim",
                            graph_scope="cross_domain", investigation_id="__operator__",
                            metadata={"chunk_id": gch})
    return {"deliverable_id": did, "section_id": sec, "node": node,
            "document": doc, "gated_node": gnode}


# ── SPR-01 — outline composition ───────────────────────────────────


def test_place_and_list_blocks(client, seed):
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    assert r.status_code == 201
    obid = r.json()["outline_block_id"]

    blocks = client.get(f"/write/sections/{seed['section_id']}/blocks").json()
    assert blocks["count"] == 1
    assert blocks["blocks"][0]["outline_block_id"] == obid
    assert blocks["blocks"][0]["node_id"] == seed["node"]


def test_place_block_rejects_orphan_prose(client, seed):
    """The no-orphan-prose invariant surfaces as a 400 over HTTP."""
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": None, "block_index": 0,
    })
    assert r.status_code == 400
    assert "no-orphan-prose" in r.json()["detail"]


def test_user_authored_block_rejects_fabricated_citation(client, seed):
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "user_authored",
        "provenance_kind": "user_authored", "node_id": seed["node"],
        "content": "x", "block_index": 0,
    })
    assert r.status_code == 400
    assert "fabricates a citation" in r.json()["detail"]


def test_outline_tree(client, seed):
    client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    tree = client.get(f"/write/deliverables/{seed['deliverable_id']}/outline").json()
    assert len(tree["roots"]) == 1
    assert tree["roots"][0]["section_id"] == seed["section_id"]
    assert len(tree["roots"][0]["blocks"]) == 1


def test_provenance_endpoint(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    prov = client.get(f"/write/blocks/{obid}/provenance").json()
    assert prov["status"] == "resolved"
    assert prov["document_id"] == seed["document"]


# ── SPR-07 — trace target (gated-source-no-leak over HTTP) ──────────


def test_trace_public_domain_opens_at_span(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    trace = client.get(f"/write/blocks/{obid}/trace").json()
    assert trace["kind"] == "source_span"
    assert trace["full_text_allowed"] is True


def test_trace_gated_book_no_leak(client, seed):
    """A gated-license source must return servable-snippet, never full text."""
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "claim",
        "provenance_kind": "graph_node", "node_id": seed["gated_node"], "block_index": 1,
    }).json()["outline_block_id"]
    trace = client.get(f"/write/blocks/{obid}/trace").json()
    assert trace["kind"] == "servable_snippet"
    assert trace["full_text_allowed"] is False  # the gate, over HTTP


# ── SPR-03 — folders + search ──────────────────────────────────────


def test_folders_and_multi_membership(client, seed):
    f1 = client.post("/write/folders", json={"name": "one"}).json()["folder_id"]
    f2 = client.post("/write/folders", json={"name": "two"}).json()["folder_id"]
    assert client.post(f"/write/folders/{f1}/blocks", json={"node_id": seed["node"]}).json()["status"] == "added"
    assert client.post(f"/write/folders/{f1}/blocks", json={"node_id": seed["node"]}).json()["status"] == "already_member"
    client.post(f"/write/folders/{f2}/blocks", json={"node_id": seed["node"]})
    folders = {f["folder_id"]: f for f in client.get("/write/folders").json()["folders"]}
    assert folders[f1]["member_count"] == 1
    assert folders[f2]["member_count"] == 1  # same node, two folders, no copy


def test_search_endpoint(client, seed):
    hits = client.get("/write/blocks/search", params={"q": "sourced insight"}).json()
    assert hits["count"] >= 1
    assert hits["hits"][0]["node_id"] == seed["node"]


# ── SPR-05 — brainstorm → user-originated blocks ───────────────────


def test_brainstorm_emit_blocks(client, seed):
    r = client.post("/write/brainstorm/emit-blocks", json={
        "section_id": seed["section_id"], "deliverable_id": seed["deliverable_id"],
        "insights": ["the moat is data"], "questions": ["does it scale?"],
        "data_points": ["80% margin"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["insight_count"] == 1 and body["question_count"] == 1 and body["data_count"] == 1
    assert len(body["flagged_unverified"]) == 1  # asserted data flagged
    # All brainstorm blocks are user-originated (no node_id / fabricated source).
    blocks = client.get(f"/write/sections/{seed['section_id']}/blocks").json()["blocks"]
    assert all(b["provenance_kind"] == "brainstorm" and b["node_id"] is None for b in blocks)


# ── SPR-08 — context promote ───────────────────────────────────────


def test_context_promote(client, seed):
    r = client.post("/write/context/promote", json={
        "title": "From context", "deliverable_kind": "general_essay",
        "objective": "argue the thesis",
        "blocks": [
            {"section_id": "ignored", "block_kind": "insight",
             "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0},
            {"section_id": "ignored", "block_kind": "user_authored",
             "provenance_kind": "brainstorm", "content": "a thought", "block_index": 1},
        ],
    })
    assert r.status_code == 201
    body = r.json()
    assert len(body["block_ids"]) == 2
    blocks = client.get(f"/write/sections/{body['section_id']}/blocks").json()
    assert blocks["count"] == 2


# ── SPR-06 — generation no-blocks → gap (no model) ─────────────────


def test_generate_empty_section_returns_gap(client, seed):
    r = client.post(f"/write/sections/{seed['section_id']}/generate")
    assert r.status_code == 200
    assert r.json()["status"] == "gap"  # never fabricated prose


def test_generate_without_credential_fails_gracefully(client, seed, monkeypatch):
    """With creative_writer wired into the dispatch config but NO provider
    credential present, generation of a section WITH blocks must degrade to
    a clean 503 ('generation unavailable') — never a 500/crash, and never
    fabricated prose. This proves the code consumes the credential
    correctly; supplying the secret itself is the operator's action."""
    for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
              "XIAOMI_API_KEY", "HERMES_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    # Attach a real block so generation is attempted (not the gap path).
    client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    r = client.post(f"/write/sections/{seed['section_id']}/generate")
    assert r.status_code == 503  # graceful, not a crash
    assert "unavailable" in r.json()["detail"].lower()
