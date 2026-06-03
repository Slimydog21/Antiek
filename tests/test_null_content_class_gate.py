"""NULL ``content_class`` is GRANDFATHERED on retrieval (search + VSS + HTTP).

ASR SR-07 proposed dropping the legacy ``content_class IS NULL OR`` carve-out
(fail-closed on NULL). That was REJECTED for #65: new ingest always writes an
explicit class via ``register_source_document``, so NULL denotes only legacy
pre-migration rows, and the codebase serves those by contract
(``test_sprint11_api::test_get_chunk_null_content_class_grandfathered``,
``test_graph``, ``test_grounding``). Re-introducing NULL-fail-closed must be
paired with a legacy-NULL → explicit-class backfill.

This test pins the grandfathered contract: NULL rows surface on the
non-privileged ``attribution_eligible`` path (and on privileged paths), and the
canonical SQL fragment keeps the ``IS NULL OR`` carve-out — with VSS /
brute_force delegating the identical gate.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_gate import (
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
    non_privileged_chunk_sql_clause,
)
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database
from substrate.graph.search import search

DOC_PUBLIC = "doc-pd-null"
DOC_LEGACY = "doc-null-legacy"
QUERY = "quantum optics null gate grandfather"


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


def test_non_privileged_sql_grandfathers_null():
    """Canon fragment keeps the ``IS NULL OR`` grandfather + the denylist."""
    sql, params = non_privileged_chunk_sql_clause(policy_tag="attribution_eligible")
    assert "content_class IS NULL" in sql
    assert "content_class NOT IN" in sql
    assert params == sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)


@pytest.fixture
def null_gate_db():
    tmp = tempfile.mkdtemp(prefix="antiek-null-grandfather-")
    db_path = os.path.join(tmp, "graph.duckdb")
    emb = StubEmbedding()
    con = connect_write(db_path, purpose="null-grandfather-seed")
    try:
        init_database(con)
        for doc_id, content_class, text in (
            (DOC_PUBLIC, "public_domain", f"{QUERY} public control"),
            (DOC_LEGACY, None, f"{QUERY} legacy null content_class"),
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
    yield {"db_path": db_path, "model": emb}


def test_search_default_policy_grandfathers_null_content_class(null_gate_db):
    """NULL ``content_class`` (legacy) surfaces on ``attribution_eligible``."""
    con = connect_read(null_gate_db["db_path"])
    try:
        res = search(
            con,
            QUERY,
            model=null_gate_db["model"],
            top_k=10,
            policy_tag="attribution_eligible",
        )
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert DOC_PUBLIC in doc_ids
    assert DOC_LEGACY in doc_ids, (
        "NULL content_class (legacy) must remain searchable — grandfathered "
        "contract; new ingest writes an explicit class so NULL = legacy only"
    )


def test_search_operator_only_includes_null_content_class(null_gate_db):
    """Privileged path has no gate clause — legacy NULL rows remain visible."""
    con = connect_read(null_gate_db["db_path"])
    try:
        res = search(
            con,
            QUERY,
            model=null_gate_db["model"],
            top_k=10,
            policy_tag="operator_only",
        )
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert DOC_LEGACY in doc_ids


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_vss_parity_grandfathers_null_on_attribution_eligible(null_gate_db, kind):
    """VSS / brute_force delegate the same canon gate as ``search()``."""
    sub = make_substrate(kind, null_gate_db["db_path"], model=null_gate_db["model"])
    try:
        res = sub.query(QUERY, top_k=10, policy_tag="attribution_eligible")
    finally:
        sub.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert DOC_PUBLIC in doc_ids
    assert DOC_LEGACY in doc_ids, (
        f"{kind} dropped NULL content_class under attribution_eligible; the "
        "grandfather carve-out must apply identically on every retrieval path"
    )
