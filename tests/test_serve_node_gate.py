"""SPR-01 — §9.0 gate on the node-match serve path.

``search_nodes_by_label`` results are returned as ``node_matches`` on the serve
payload (``substrate/graph/search.py::search`` and
``retrieval_substrate.py``) and read by the LLM. Before this sprint the query
was a bare ``WHERE canonical_label ILIKE ?`` with NO content-class gate, so a
``personal_reading`` node label (owner's private third-party reading, ingested
via inbox / substack) leaked to a non-owner serve — the exact §9.0 leak the
chunk path already blocks.

This test seeds one ``personal_reading`` document and one servable document,
each producing a labeled node whose provenance rides on ``node.metadata.chunk_id``
(the real inbox/substack shape — those connectors write NO edge). It then
exercises the ACTUAL serve payload (``search(...)["node_matches"]``), not an
internal helper, in both directions:

  * non-privileged (default ``attribution_eligible``): personal label ABSENT,
    servable label PRESENT;
  * owner / privileged (``operator_only``): BOTH present.

RED-PROVEN: with the SPR-01 gate reverted (bare ILIKE), the non-privileged
assertion fails because the personal label is returned — proving the test
exercises the gate and is not a fake gate (see the sprint handoff for the
captured pre-fix failure).
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from processing.embedding.embed import HashEmbedding  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.graph import (  # noqa: E402
    init_database_at_path,
    insert_chunk,
    insert_document,
    insert_node,
    search,
)

_PERSONAL_LABEL = "Zebra Quartet Personal Headline"
_PUBLIC_LABEL = "Zebra Quartet Public Headline"
# A servable class: anything NOT in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES.
_SERVABLE_CONTENT_CLASS = "user_owned"


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def seeded_db(tmp_path) -> str:
    """DB with a personal_reading node and a servable node, each grounded on a
    chunk via ``node.metadata.chunk_id`` (the inbox/substack provenance shape —
    no edge). Both labels share the query token so a single ILIKE matches both;
    only the §9.0 gate should separate them."""
    p = str(tmp_path / "graph.duckdb")
    init_database_at_path(p)
    emb = HashEmbedding()
    con = connect_write(p, purpose="seed")
    try:
        for doc_id, content_class, label, body in (
            ("doc-personal", PERSONAL_READING_CONTENT_CLASS, _PERSONAL_LABEL,
             f"{_PERSONAL_LABEL}\nowner private reading body"),
            ("doc-public", _SERVABLE_CONTENT_CLASS, _PUBLIC_LABEL,
             f"{_PUBLIC_LABEL}\npublic servable body"),
        ):
            insert_document(
                con,
                document_id=doc_id,
                source_tier=3,
                document_type="url",
                content_class=content_class,
                investigation_id="seed",
                on_conflict="ignore",
            )
            chunk_id = insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                text=body,
                section_path=None,
                embedding=emb.encode(body),
                token_count=len(body.split()),
            )
            insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id="seed",
                embedding=emb.encode(label),
                # inbox/substack shape: grounding chunk in metadata, NO edge.
                metadata={"source": "inbox", "chunk_id": chunk_id,
                          "document_id": doc_id},
                on_conflict="ignore",
            )
    finally:
        con.close()
    return p


def _labels(db_path: str, *, policy_tag: str) -> set[str]:
    """The actual ``node_matches`` labels the serve payload returns."""
    emb = HashEmbedding()
    con = connect_read(db_path)
    try:
        result = search(
            con, "Zebra Quartet", model=emb, top_k=5, policy_tag=policy_tag,
        )
    finally:
        con.close()
    return {n["label"] for n in result["node_matches"]}


def test_non_privileged_excludes_personal_includes_public(seeded_db):
    # Default serve tag (attribution_eligible) — the monetized / non-owner path.
    labels = _labels(seeded_db, policy_tag="attribution_eligible")
    assert _PERSONAL_LABEL not in labels, (
        "§9.0 LEAK: personal_reading node label served on non-privileged path"
    )
    assert _PUBLIC_LABEL in labels, (
        "servable node label wrongly withheld on non-privileged path"
    )


def test_forgotten_policy_tag_is_safe_by_default(seeded_db):
    # A caller that omits policy_tag entirely must get the GATED result — the
    # default is the non-privileged (safe) value, so a leak is impossible.
    emb = HashEmbedding()
    con = connect_read(seeded_db)
    try:
        result = search(con, "Zebra Quartet", model=emb, top_k=5)
    finally:
        con.close()
    labels = {n["label"] for n in result["node_matches"]}
    assert _PERSONAL_LABEL not in labels
    assert _PUBLIC_LABEL in labels


def test_owner_path_includes_both(seeded_db):
    # Owner / privileged path returns every labeled node, personal included.
    labels = _labels(seeded_db, policy_tag="operator_only")
    assert _PERSONAL_LABEL in labels
    assert _PUBLIC_LABEL in labels
    labels_pr = _labels(seeded_db, policy_tag="private_research")
    assert _PERSONAL_LABEL in labels_pr
    assert _PUBLIC_LABEL in labels_pr
