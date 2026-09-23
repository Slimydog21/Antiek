"""The synthesis export's provenance gate counts every manifest pin.

``resolve_synthesis_export`` is exercised against a real graph (the route tests
in ``test_synthesis_artifact.py`` mock it). A document pin whose ``documents``
row is gone must reach the adapter as an unresolved source, so the M4 gate
reports the claim as not fully sourced; dropping it before the gate would let
a synthesis that lost two of three sources export as "complete".
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import synthesis_artifact as mod
from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized


@pytest.fixture
def graph(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="syn-resolver-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    ensure_initialized(db)
    con = connect_write(db)
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "content_class, ip_holder_id, title) VALUES (?,?,?,?,?,?)",
            ["doc-ok", 1, "article", "public_domain", None, "Surviving source"],
        )
        for sid, pins in (
            ("s-partial", ("doc-ok", "doc-gone-1", "doc-gone-2")),
            ("s-whole", ("doc-ok",)),
        ):
            con.execute(
                "INSERT INTO syntheses (synthesis_id, target_question, "
                "synthesis_timestamp, status, implicit_recommendation, thesis_text) "
                "VALUES (?, ?, now(), 'passed', 'proceed', ?)",
                [sid, f"Q {sid}", f"Thesis of {sid}"],
            )
            for doc in pins:
                con.execute(
                    "INSERT INTO synthesis_substrate_manifest "
                    "(synthesis_id, entity_kind, entity_id) VALUES (?, 'document', ?)",
                    [sid, doc],
                )
    finally:
        con.close()
    return db


def _html(synthesis_id: str) -> str:
    app = FastAPI()
    mod.register_synthesis_artifact_routes(app)
    resp = TestClient(app).get(f"/api/syntheses/{synthesis_id}/artifact.html")
    assert resp.status_code == 200, resp.text[:300]
    return resp.text


def test_dangling_manifest_pins_count_against_completeness(graph):
    export = mod.resolve_synthesis_export("s-partial", db_path=graph)
    assert export is not None
    (claim,) = export.claims
    assert len(claim.sources) == 3, "a dangling pin was dropped before the gate"
    assert [s.resolved for s in claim.sources].count(True) == 1
    assert claim.fully_sourced is False
    # A pin with no documents row names no document: it is not cited, and it
    # carries no attribution entry a payout could be computed from.
    assert set(export.attribution_manifest["document_ip_holders"]) == {"doc-ok"}

    html = _html("s-partial")
    assert "Provenance incomplete — 0 of 1 claims fully sourced." in html
    assert "(unsourced)" in html


def test_fully_pinned_synthesis_still_reports_complete(graph):
    export = mod.resolve_synthesis_export("s-whole", db_path=graph)
    assert export is not None
    (claim,) = export.claims
    assert [s.document_id for s in claim.sources] == ["doc-ok"]
    assert claim.fully_sourced is True
    html = _html("s-whole")
    assert "Provenance incomplete" not in html
    assert "(unsourced)" not in html


# ── every pin kind reaches the gate (chunk / node / edge, not only document) ──

SECRET = "SECRET PAYWALLED PASSAGE quoted verbatim in the thesis"


@pytest.fixture
def pinned(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="syn-pins-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    ensure_initialized(db)
    con = connect_write(db)
    try:
        for doc_id, cls, holder in (
            ("doc-ok", "public_domain", None),
            ("doc-pr", "personal_reading", "holder-x"),
        ):
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, ip_holder_id, title) VALUES (?,?,?,?,?,?)",
                [doc_id, 1, "article", cls, holder, f"Title {doc_id}"],
            )
        for chunk_id, doc_id, text in (
            ("c-ok-1", "doc-ok", "public text one"),
            ("c-ok-2", "doc-ok", "public text two"),
            ("c-pr", "doc-pr", SECRET),
        ):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES (?,?,0,?)",
                [chunk_id, doc_id, text],
            )
        for node_id in ("n-a", "n-b"):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, 'entity', 'depth')",
                [node_id, node_id],
            )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata) VALUES ('n-claim', 'a claim', 'claim', 'depth', ?)",
            ['{"source_document_id": "doc-ok"}'],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-unsourced', 'an unsupported claim', 'claim', 'depth')"
        )
        for node_id, meta in (
            ("n-meta-chunk-gone", '{"source_document_id": "doc-ok", "chunk_id": "c-gone"}'),
            ("n-mixed", '{"source_document_id": "doc-ok"}'),
            ("n-chunk-only", '{"chunk_id": "c-pr"}'),
        ):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
                "metadata) VALUES (?, 'a claim', 'claim', 'depth', ?)",
                [node_id, meta],
            )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-mixed', 'n-mixed', 'n-b', 'supported_by', 'doc-pr', 1, 0.9, 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-ok', 'n-a', 'n-b', 'rel', 'c-ok-1', 1, 0.9, 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-structural', 'n-a', 'n-b', 'rel2', 1, 0.9, 'depth')"
        )
        for sid, thesis, pins in (
            # codex's reproduction: one valid document pin + one missing chunk pin.
            ("s-doc-chunk-gone", "Thesis A", (("document", "doc-ok"), ("chunk", "c-gone"))),
            # A live chunk pin (what the archive writer actually pins) resolves
            # to its document; two chunks of one document cite it once.
            ("s-chunks", "Thesis B", (("chunk", "c-ok-1"), ("chunk", "c-ok-2"))),
            ("s-edge-node", "Thesis C", (("edge", "e-ok"), ("edge", "e-structural"),
                                         ("node", "n-claim"), ("node", "n-a"))),
            ("s-edge-node-gone", "Thesis D", (("chunk", "c-ok-1"), ("edge", "e-gone"),
                                              ("node", "n-gone"),
                                              ("node", "n-unsourced"))),
            ("s-restricted", f"Thesis quoting it: {SECRET}",
             (("chunk", "c-ok-1"), ("chunk", "c-pr"))),
            ("s-node-chunk-gone", "Thesis E", (("node", "n-meta-chunk-gone"),)),
            ("s-node-mixed", f"Thesis quoting it: {SECRET}", (("node", "n-mixed"),)),
            ("s-node-chunk-only", f"Thesis quoting it: {SECRET}",
             (("node", "n-chunk-only"),)),
        ):
            con.execute(
                "INSERT INTO syntheses (synthesis_id, target_question, "
                "synthesis_timestamp, status, implicit_recommendation, thesis_text) "
                "VALUES (?, ?, now(), 'passed', 'proceed', ?)",
                [sid, f"Q {sid}", thesis],
            )
            for kind, eid in pins:
                con.execute(
                    "INSERT INTO synthesis_substrate_manifest "
                    "(synthesis_id, entity_kind, entity_id) VALUES (?, ?, ?)",
                    [sid, kind, eid],
                )
    finally:
        con.close()
    return db


def test_missing_chunk_pin_counts_against_completeness(pinned):
    export = mod.resolve_synthesis_export("s-doc-chunk-gone", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert len(claim.sources) == 2, [s.document_id for s in claim.sources]
    assert [s.resolved for s in claim.sources] == [True, False]
    assert claim.fully_sourced is False
    html = _html("s-doc-chunk-gone")
    assert "Provenance incomplete — 0 of 1 claims fully sourced." in html
    assert "(unsourced)" in html


def test_live_chunk_pins_resolve_to_their_document(pinned):
    export = mod.resolve_synthesis_export("s-chunks", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert [s.document_id for s in claim.sources] == ["doc-ok"]
    assert claim.fully_sourced is True
    assert export.attribution_manifest["document_ip_holders"] == {"doc-ok": None}
    html = _html("s-chunks")
    assert "Provenance incomplete" not in html
    assert "Thesis B" in html


def test_edge_and_node_pins_resolve_through_their_grounding(pinned):
    # e-ok grounds on c-ok-1 (doc-ok); n-claim names doc-ok; a structural edge
    # and an entity node carry no source and are not provenance.
    export = mod.resolve_synthesis_export("s-edge-node", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert [s.document_id for s in claim.sources] == ["doc-ok"]
    assert claim.fully_sourced is True


def test_missing_edge_and_node_pins_are_unresolved(pinned):
    export = mod.resolve_synthesis_export("s-edge-node-gone", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    # doc-ok via c-ok-1, then the missing edge, the missing node and the claim
    # node that names no source: three unresolved pins.
    assert [s.resolved for s in claim.sources] == [True, False, False, False]
    assert claim.fully_sourced is False


def test_thesis_standing_on_a_restricted_chunk_is_withheld(pinned):
    # The sibling of the research-artifact excerpt leak: the synthesis export
    # carried the thesis prose in full while its only record of the gated
    # source was a chunk pin the resolver never read.
    export = mod.resolve_synthesis_export("s-restricted", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert {s.document_id for s in claim.sources} == {"doc-ok", "doc-pr"}
    html = _html("s-restricted")
    assert SECRET not in html
    assert "cite-only" in html
    assert "withheld" in html


# ── a node pin grounds on every pointer it carries, not only the first ──


def test_node_pin_with_a_missing_metadata_chunk_is_unresolved(pinned):
    # codex's reproduction: the node names a live public document and a chunk
    # that is gone. The document alone reported the claim fully sourced.
    export = mod.resolve_synthesis_export("s-node-chunk-gone", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert [(s.document_id, s.resolved) for s in claim.sources] == [
        ("doc-ok", True), (None, False),
    ]
    assert claim.fully_sourced is False
    assert "Provenance incomplete" in _html("s-node-chunk-gone")


def test_node_pin_follows_every_supported_by_edge(pinned):
    # Metadata names doc-ok; a supported_by edge grounds the same node on the
    # personal-reading essay. The thesis quoting it must not export.
    export = mod.resolve_synthesis_export("s-node-mixed", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert [s.document_id for s in claim.sources] == ["doc-ok", "doc-pr"]
    html = _html("s-node-mixed")
    assert SECRET not in html
    assert "withheld" in html


def test_node_pin_grounds_through_its_metadata_chunk(pinned):
    # The inbox/substack ingest link: the node records only its chunk.
    export = mod.resolve_synthesis_export("s-node-chunk-only", db_path=pinned)
    assert export is not None
    (claim,) = export.claims
    assert [s.document_id for s in claim.sources] == ["doc-pr"]
    assert SECRET not in _html("s-node-chunk-only")
