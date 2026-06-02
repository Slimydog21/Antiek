"""SR-02 — VSS + brute-force substrates use retrieval_gate on attribution_eligible.

Pins that personal_reading chunks are excluded under the default policy_tag
for BOTH substrate impls (the pre-SR-02 RESTRICTED-only VSS path would leak).
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database


class StubEmbedding:
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
def pr_substrate_db():
    tmp = tempfile.mkdtemp(prefix="antiek-sr02-vss-pr-")
    db_path = os.path.join(tmp, "graph.duckdb")
    emb = StubEmbedding()
    con = connect_write(db_path, purpose="sr02-vss-pr-seed")
    try:
        init_database(con)
        for doc_id, content_class, text in (
            ("doc-pd", "public_domain", "quantum optics public control SR02"),
            ("doc-pr", "personal_reading", "quantum optics personal reading SR02"),
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
    finally:
        con.close()
    yield db_path, emb


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_substrate_default_policy_tag_excludes_personal_reading(
    pr_substrate_db, kind,
):
    db_path, emb = pr_substrate_db
    sub = make_substrate(kind, db_path, model=emb)
    try:
        res = sub.query(
            "quantum optics",
            top_k=10,
            policy_tag="attribution_eligible",
        )
    finally:
        sub.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pd" in doc_ids
    assert "doc-pr" not in doc_ids, (
        f"{kind} leaked personal_reading under attribution_eligible"
    )


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_substrate_operator_only_includes_personal_reading(
    pr_substrate_db, kind,
):
    db_path, emb = pr_substrate_db
    sub = make_substrate(kind, db_path, model=emb)
    try:
        res = sub.query(
            "quantum optics",
            top_k=10,
            policy_tag="operator_only",
        )
    finally:
        sub.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pr" in doc_ids, (
        f"{kind} withheld personal_reading under operator_only"
    )