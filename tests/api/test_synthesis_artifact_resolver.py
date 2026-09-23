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
