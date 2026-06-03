"""§9.0 regression — the lexical (keyword) retrieval path MUST apply the
same non-privileged chunk gate as the embedding path.

The leak this guards: ``orchestration.loop_one.orchestrator._keyword_search_chunks``
was a raw ``SELECT ... FROM chunks JOIN documents WHERE <LIKE>`` with NO
content_class gate, while the embedding path (``substrate.graph.search.search``)
gated correctly. So a ``restricted_pending_opt_in`` / ``personal_reading`` chunk
that matched a keyword would leak into research evidence on the non-privileged
``attribution_eligible`` lane — a money-path retrieval-gate leak (master-spec
§9.0). Both retrieval paths must gate identically.

These tests are NON-VACUOUS: they seed one servable + one restricted + one
personal_reading doc that ALL match the query keyword, then assert the gate
withholds the two gated classes on the public lane and the privileged
owner-read lane sees all three.
"""

from __future__ import annotations

import os
import tempfile

import duckdb

from orchestration.loop_one.orchestrator import _keyword_search_chunks
from runtime.db_lock import connect_write
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database

_KEYWORD = "quantumoptics"
DOC_PUBLIC = "doc-public"
DOC_RESTRICTED = "doc-restricted"
DOC_PERSONAL = "doc-personal"


def _seed(db_path: str) -> None:
    con = connect_write(db_path, purpose="keyword-gate-seed")
    try:
        init_database(con)
        for doc_id, content_class in (
            (DOC_PUBLIC, "public_domain"),
            (DOC_RESTRICTED, GATED_DEFAULT_CONTENT_CLASS),
            (DOC_PERSONAL, PERSONAL_READING_CONTENT_CLASS),
        ):
            insert_document(
                con,
                document_id=doc_id,
                source_tier=2,
                document_type="academic_paper",
                title=f"Title {doc_id}",
                content_class=content_class,
            )
            insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                # All three match the keyword so the ONLY thing that can
                # exclude a row is the §9.0 gate, not the LIKE. The text is
                # made DISTINCT per doc (``{doc_id}``) because chunk_id is
                # content-addressed from the text — identical text would dedupe
                # to one row and silently defeat the test.
                text=f"a study of {_KEYWORD} and reasoning in {doc_id}",
                token_count=10,
                embedding=[0.1, 0.2, 0.3, 0.4],
            )
    finally:
        con.close()


def _doc_ids(rows: list[dict]) -> set[str]:
    # _keyword_search_chunks returns chunk rows; map back via title convention.
    return {r["document_title"].replace("Title ", "") for r in rows}


def test_keyword_path_withholds_gated_classes_on_public_lane():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "graph.duckdb")
        _seed(db)
        con = duckdb.connect(db, read_only=True)
        try:
            rows = _keyword_search_chunks(
                con, [_KEYWORD], top_k=10, policy_tag="attribution_eligible"
            )
        finally:
            con.close()
    ids = _doc_ids(rows)
    assert DOC_PUBLIC in ids, "servable public_domain chunk must be retrievable"
    assert DOC_RESTRICTED not in ids, (
        "LEAK: restricted_pending_opt_in chunk surfaced on the keyword path "
        "under attribution_eligible — the §9.0 gate is not applied"
    )
    assert DOC_PERSONAL not in ids, (
        "LEAK: personal_reading chunk surfaced on the keyword path under "
        "attribution_eligible — the §9.0 gate is not applied"
    )


def test_keyword_path_owner_lane_sees_all():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "graph.duckdb")
        _seed(db)
        con = duckdb.connect(db, read_only=True)
        try:
            rows = _keyword_search_chunks(
                con, [_KEYWORD], top_k=10, policy_tag="private_research"
            )
        finally:
            con.close()
    ids = _doc_ids(rows)
    assert {DOC_PUBLIC, DOC_RESTRICTED, DOC_PERSONAL} <= ids, (
        "the privileged private_research owner-read lane must see the owner's "
        "own restricted + personal_reading documents (no gate clause)"
    )


def test_keyword_path_default_policy_is_public_lane():
    # The default arg must be the safe (gated) lane, not a leak-by-default.
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "graph.duckdb")
        _seed(db)
        con = duckdb.connect(db, read_only=True)
        try:
            rows = _keyword_search_chunks(con, [_KEYWORD], top_k=10)
        finally:
            con.close()
    ids = _doc_ids(rows)
    assert DOC_RESTRICTED not in ids and DOC_PERSONAL not in ids, (
        "default policy_tag must gate (deny-by-default), never leak gated classes"
    )
