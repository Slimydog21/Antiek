"""WV-SPR-01 — multi-section coherence at the generate route (§10.6).

Exercises ``write_router`` in isolation (mounted on a bare app, so it needs
none of the ``create_app`` boot surface): the ``/write/sections/{id}/generate``
route must hand ``creative_writer`` the section's REAL outline position and the
deliverable's OTHER sections — prior sections carrying their prose so the model
does not repeat them, upcoming sections carrying only a title — instead of the
single-section placeholder (index 0 of 1, no neighbours) it used before.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import write_routes  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_node,
    insert_section,
)
from substrate.write.draft_generation import GateResult, GenerationResult  # noqa: E402
from substrate.write.outline_block import place_block  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db = str(tmp_path / "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(default_db_path())
    return db


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(write_routes.write_router)
    return TestClient(app)


def test_generate_passes_real_position_and_adjacent_sections(client, monkeypatch):
    """The generate route hands creative_writer the section's real position and
    the deliverable's other sections, proven by capturing the
    CreativeWriterContext the route builds and reads."""
    with connect_write(default_db_path(), purpose="test/coherence-seed") as con:
        did = insert_deliverable(con, title="Three-part memo",
                                 deliverable_kind="research_memo")
        s1 = insert_section(con, deliverable_id=did, section_index=0, title="Origins")
        s2 = insert_section(con, deliverable_id=did, section_index=1, title="The turn")
        s3 = insert_section(con, deliverable_id=did, section_index=2, title="Consequences")
        con.execute("UPDATE deliverable_sections SET prose_text=? WHERE section_id=?",
                    ["Origins prose.", s1])
        con.execute("UPDATE deliverable_sections SET prose_text=? WHERE section_id=?",
                    ["The turn prose.", s2])
        doc = insert_document(con, document_id="doc-c", source_tier=2,
                              document_type="book", title="Src")
        con.execute("UPDATE documents SET content_class='public_domain' "
                    "WHERE document_id=?", [doc])
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="an insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
        place_block(con, section_id=s3, block_kind="insight",
                    provenance_kind="graph_node", block_index=0,
                    node_id=node, deliverable_id=did)

    captured: dict = {}

    def _spy(*, ctx, dispatch_fn, section_id):
        captured["ctx"] = ctx
        return GenerationResult(
            status="generated", section_id=section_id,
            prose_text=f"Draft [b: {node}].", citation_report=None,
            gate=GateResult(score=0.9, passed=True, violations=[]),
        )

    monkeypatch.setattr(write_routes, "generate_section", _spy)

    r = client.post(f"/write/sections/{s3}/generate")
    assert r.status_code == 200, r.text

    ctx = captured["ctx"]
    # Real outline position, not the 0-of-1 placeholder.
    assert ctx.section_count == 3
    assert ctx.section_index == 2
    # The two prior sections are present WITH their prose; the section being
    # generated is not listed among its own neighbours.
    adj = {a.title: a for a in ctx.adjacent_sections}
    assert set(adj) == {"Origins", "The turn"}
    assert adj["Origins"].prose_text == "Origins prose."
    assert adj["The turn"].prose_text == "The turn prose."
    assert all(a.section_index < ctx.section_index for a in ctx.adjacent_sections)


def test_single_section_deliverable_has_no_neighbours(client, monkeypatch):
    """A one-section deliverable must pass an empty neighbour list and a real
    count of 1 — the coherence wiring must not fabricate neighbours."""
    with connect_write(default_db_path(), purpose="test/coherence-solo") as con:
        did = insert_deliverable(con, title="Solo", deliverable_kind="general_essay")
        s1 = insert_section(con, deliverable_id=did, section_index=0, title="Only")
        doc = insert_document(con, document_id="doc-s", source_tier=2,
                              document_type="book", title="Src")
        con.execute("UPDATE documents SET content_class='public_domain' "
                    "WHERE document_id=?", [doc])
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="an insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
        place_block(con, section_id=s1, block_kind="insight",
                    provenance_kind="graph_node", block_index=0,
                    node_id=node, deliverable_id=did)

    captured: dict = {}

    def _spy(*, ctx, dispatch_fn, section_id):
        captured["ctx"] = ctx
        return GenerationResult(
            status="generated", section_id=section_id,
            prose_text=f"Draft [b: {node}].", citation_report=None,
            gate=GateResult(score=0.9, passed=True, violations=[]),
        )

    monkeypatch.setattr(write_routes, "generate_section", _spy)

    r = client.post(f"/write/sections/{s1}/generate")
    assert r.status_code == 200, r.text
    ctx = captured["ctx"]
    assert ctx.section_count == 1
    assert ctx.section_index == 0
    assert ctx.adjacent_sections == []


def test_generating_early_section_marks_later_sections_upcoming(client, monkeypatch):
    """Generating an EARLY section: later sections must be classified UPCOMING
    (title only, prose_text=None) even when they ALREADY hold prose in the DB
    (generated out of order) — the model must never receive downstream prose as
    don't-repeat context. Guards the i<this_index classifier against leaking
    future prose (a flip to i!=this_index would pass every last-section test)."""
    with connect_write(default_db_path(), purpose="test/coherence-upcoming") as con:
        did = insert_deliverable(con, title="Ordered memo",
                                 deliverable_kind="research_memo")
        s1 = insert_section(con, deliverable_id=did, section_index=0, title="Intro")
        s2 = insert_section(con, deliverable_id=did, section_index=1, title="Body")
        s3 = insert_section(con, deliverable_id=did, section_index=2, title="End")
        # Later sections already have prose (out-of-order generation) — it must
        # NOT reach the model when generating the earlier Intro.
        con.execute("UPDATE deliverable_sections SET prose_text=? WHERE section_id=?",
                    ["Body prose already written.", s2])
        con.execute("UPDATE deliverable_sections SET prose_text=? WHERE section_id=?",
                    ["End prose already written.", s3])
        doc = insert_document(con, document_id="doc-u", source_tier=2,
                              document_type="book", title="Src")
        con.execute("UPDATE documents SET content_class='public_domain' "
                    "WHERE document_id=?", [doc])
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="an insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
        place_block(con, section_id=s1, block_kind="insight",
                    provenance_kind="graph_node", block_index=0,
                    node_id=node, deliverable_id=did)

    captured: dict = {}

    def _spy(*, ctx, dispatch_fn, section_id):
        captured["ctx"] = ctx
        return GenerationResult(
            status="generated", section_id=section_id,
            prose_text=f"Draft [b: {node}].", citation_report=None,
            gate=GateResult(score=0.9, passed=True, violations=[]),
        )

    monkeypatch.setattr(write_routes, "generate_section", _spy)

    r = client.post(f"/write/sections/{s1}/generate")
    assert r.status_code == 200, r.text
    ctx = captured["ctx"]
    assert ctx.section_index == 0
    assert ctx.section_count == 3
    adj = {a.title: a for a in ctx.adjacent_sections}
    assert set(adj) == {"Body", "End"}
    # Upcoming sections carry NO prose, even though the DB has it for them.
    assert adj["Body"].prose_text is None
    assert adj["End"].prose_text is None
    assert all(a.section_index > ctx.section_index for a in ctx.adjacent_sections)
