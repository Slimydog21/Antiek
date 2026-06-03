"""RG-05 — Cross-surface retrieval gate closure matrix.

One synthetic DuckDB fixture (one ``personal_reading`` chunk + one
``public_domain`` control, distinct bodies) is probed four ways:

  - ``search()``
  - ``make_substrate("vss").query()``
  - ``make_substrate("brute_force").query()``
  - ``TestClient`` ``GET /chunks/{id}``

All three retrieval surfaces must agree on §9.0 policy_tag gating; the HTTP
chunk path must withhold ``personal_reading`` on the non-privileged gate.
``compute_attribution_for_synthesis`` must still drop ``personal_reading``
(regression pin).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.graph.ops import insert_chunk, insert_document  # noqa: E402
from substrate.graph.retrieval_substrate import make_substrate  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from substrate.graph.search import search  # noqa: E402

DOC_PUBLIC = "doc-pd"
DOC_PERSONAL = "doc-pr"
# Distinct bodies — content-addressed chunk_id would collide on identical text.
TEXT_PUBLIC = "quantum optics public domain control chunk RG05 closure"
TEXT_PERSONAL = "quantum optics personal reading owner lane chunk RG05 closure"
QUERY = "quantum optics"


class StubEmbedding:
    """Deterministic length-4 embedding (no sentence-transformers)."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def gate_closure_db():
    """Single fixture graph: personal_reading + public_domain control."""
    tmp = tempfile.mkdtemp(prefix="antiek-rg05-closure-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    emb = StubEmbedding()
    con = connect_write(db_path, purpose="rg05-closure-seed")
    try:
        init_database(con)
        for doc_id, content_class, text in (
            (DOC_PUBLIC, "public_domain", TEXT_PUBLIC),
            (DOC_PERSONAL, "personal_reading", TEXT_PERSONAL),
        ):
            insert_document(
                con,
                document_id=doc_id,
                source_tier=2,
                document_type="paper",
                title=f"Title {doc_id}",
                content_class=content_class,
            )
            insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                text=text,
                token_count=10,
                embedding=emb.encode(text),
            )
        personal_chunk_id = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            [DOC_PERSONAL],
        ).fetchone()[0]
    finally:
        con.close()
    yield {
        "db_path": db_path,
        "events_dir": events_dir,
        "model": emb,
        "personal_chunk_id": personal_chunk_id,
    }


def _retrieval_probe(
    db_path: str,
    model: StubEmbedding,
    *,
    surface: str,
    policy_tag: str,
    top_k: int = 10,
) -> dict:
    """Run the same query on search, vss, or brute_force."""
    if surface == "search":
        con = connect_read(db_path)
        try:
            return search(
                con,
                QUERY,
                model=model,
                top_k=top_k,
                policy_tag=policy_tag,
            )
        finally:
            con.close()
    sub = make_substrate(surface, db_path, model=model)
    try:
        return sub.query(QUERY, top_k=top_k, policy_tag=policy_tag)
    finally:
        sub.close()


def _document_ids(result: dict) -> set[str]:
    return {r["document_id"] for r in result["results"]}


@pytest.mark.parametrize("surface", ["search", "vss", "brute_force"])
def test_attribution_eligible_excludes_personal_reading(gate_closure_db, surface):
    """Non-privileged path: public control retrievable, personal_reading withheld."""
    db = gate_closure_db
    res = _retrieval_probe(
        db["db_path"],
        db["model"],
        surface=surface,
        policy_tag="attribution_eligible",
    )
    doc_ids = _document_ids(res)
    assert DOC_PUBLIC in doc_ids, f"{surface} lost public_domain control"
    assert DOC_PERSONAL not in doc_ids, (
        f"{surface} leaked personal_reading under attribution_eligible"
    )


@pytest.mark.parametrize("surface", ["search", "vss", "brute_force"])
def test_operator_only_includes_personal_reading(gate_closure_db, surface):
    """Privileged owner path: personal_reading retrievable alongside control."""
    db = gate_closure_db
    res = _retrieval_probe(
        db["db_path"],
        db["model"],
        surface=surface,
        policy_tag="operator_only",
    )
    doc_ids = _document_ids(res)
    assert DOC_PUBLIC in doc_ids, f"{surface} lost public_domain under operator_only"
    assert DOC_PERSONAL in doc_ids, (
        f"{surface} withheld personal_reading under operator_only"
    )


def test_get_chunk_withholds_personal_reading_body(gate_closure_db, monkeypatch):
    """HTTP chunk surface aligns with retrieval gate — body withheld."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", gate_closure_db["db_path"])
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", gate_closure_db["events_dir"])
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    client = TestClient(app)
    body = client.get(f"/chunks/{gate_closure_db['personal_chunk_id']}").json()
    assert body["servable"] is False
    # Canonical ASR SR-09 label (consolidation: #53's "personal_only" unified to
    # the ASR contract, pinned by test_get_chunk_personal_reading + the matrix).
    assert body["servability"] == "personal_readable"
    assert body["text"] == ""
    assert TEXT_PERSONAL not in body["text"]
    assert body["document_id"] == DOC_PERSONAL


def test_compute_attribution_drops_personal_reading(gate_closure_db, monkeypatch):
    """Regression: attribution compute must exclude personal_reading shares."""
    from substrate.attribution.compute import compute_attribution_for_synthesis

    db_path = gate_closure_db["db_path"]
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    emb = gate_closure_db["model"]
    con = connect_write(db_path, purpose="rg05-syn")
    try:
        chunk_ids: list[str] = []
        for doc_id, content_class, text in (
            (DOC_PUBLIC, "public_domain", "public servable synthesis cite RG05"),
            (DOC_PERSONAL, "personal_reading", "owner-private synthesis cite RG05"),
        ):
            insert_document(
                con,
                document_id=doc_id,
                source_tier=2,
                document_type="paper",
                title=f"Title {doc_id}",
                content_class=content_class,
                on_conflict="ignore",
            )
            chunk_ids.append(
                insert_chunk(
                    con,
                    document_id=doc_id,
                    chunk_index=0,
                    text=text,
                    token_count=10,
                    embedding=emb.encode(text),
                )
            )
        thesis = {
            "thesis_components": [
                {
                    "claim": "C1",
                    "confidence": "high",
                    "supporting_chunk_ids": chunk_ids,
                },
            ],
        }
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-rg05", "inv-rg05", "Q?", "passed", "proceed", json.dumps(thesis)],
        )
    finally:
        con.close()

    r = compute_attribution_for_synthesis("syn-rg05", db_path=db_path)
    for opt in (r.option_a, r.option_b, r.option_c):
        assert DOC_PERSONAL not in opt.shares, opt.algorithm
        assert DOC_PERSONAL not in opt.document_titles, opt.algorithm
    assert r.option_b.shares == pytest.approx({DOC_PUBLIC: 1.0})