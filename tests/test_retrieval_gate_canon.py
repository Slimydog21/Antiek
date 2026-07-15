"""SR-01 — retrieval_gate.py is the single non-privileged chunk-filter SQL emitter.

Pins the canonical denylist (restricted_pending_opt_in + personal_reading),
the NULL ``IS NULL OR`` grandfather carve-out (legacy rows stay searchable —
SR-07's fail-closed flip is deferred behind the SR-06 prod backfill,
GATE-BACKFILL-DONE, and was dropped from #65), and search() delegation so a
RESTRICTED-only revert cannot slip personal_reading onto the default policy_tag
path.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_gate import (
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
    PERSONAL_ONLY_CONTENT_CLASSES,
    RESTRICTED_CONTENT_CLASSES,
    non_privileged_chunk_sql_clause,
)
from substrate.graph.schema import init_database
from substrate.graph.search import search


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


def test_non_privileged_excluded_union_includes_personal_reading():
    assert "personal_reading" in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES
    assert PERSONAL_ONLY_CONTENT_CLASSES <= _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES


def test_restricted_only_predicate_would_leak_personal_reading():
    """RESTRICTED-only SQL is NOT equivalent to the canonical union gate."""
    assert "personal_reading" not in RESTRICTED_CONTENT_CLASSES
    assert "personal_reading" in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES


def test_default_policy_tag_clause_binds_full_denylist():
    sql, params = non_privileged_chunk_sql_clause(policy_tag="attribution_eligible")
    # NULL content_class is GRANDFATHERED (legacy rows stay searchable); the
    # SR-07 fail-closed flip was rejected for #65 (see retrieval_gate docstring).
    assert "content_class IS NULL" in sql
    assert "content_class NOT IN" in sql
    assert "personal_reading" in params
    assert "restricted_pending_opt_in" in params
    assert params == sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)


def test_privileged_policy_tag_retains_owner_boundary():
    for tag in ("private_research", "operator_only"):
        sql, params = non_privileged_chunk_sql_clause(policy_tag=tag)
        assert "owner_user_id = ?" in sql
        assert params[-1] == "__operator__"
        assert set(params[:-1]) == PERSONAL_ONLY_CONTENT_CLASSES


@pytest.fixture
def gate_db():
    tmp = tempfile.mkdtemp(prefix="antiek-sr01-gate-")
    db_path = os.path.join(tmp, "graph.duckdb")
    emb = StubEmbedding()
    con = connect_write(db_path, purpose="sr01-gate-seed")
    try:
        init_database(con)
        for doc_id, content_class, text in (
            ("doc-pd", "public_domain", "quantum optics public control SR01"),
            ("doc-pr", "personal_reading", "quantum optics personal reading SR01"),
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


def test_search_default_policy_tag_excludes_personal_reading(gate_db):
    """Default policy_tag must not return personal_reading chunks."""
    con = connect_read(gate_db["db_path"])
    try:
        res = search(
            con,
            "quantum optics",
            model=gate_db["model"],
            top_k=10,
            policy_tag="attribution_eligible",
        )
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pd" in doc_ids
    assert "doc-pr" not in doc_ids, "personal_reading leaked under default policy_tag"
