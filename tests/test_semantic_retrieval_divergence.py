"""DOGFOOD SPR-02 M4 — the semantic-vs-hash divergence red-proof.

The load-bearing proof that upgrading the embedding provider actually
changes retrieval, not just the stored vectors. A tiny fixture corpus is
constructed so the hash neighbour and the semantic neighbour are PROVABLY
DIFFERENT: a query whose semantic target shares no keywords (so
HashEmbedding's token-bag misses it) while a distractor shares keywords
(so HashEmbedding's top-1 is the wrong, off-topic chunk).
SentenceTransformerEmbedding must surface the semantic target as top-1.

Hermetic: tmp DuckDB initialized per test. The sentence-transformers
model is the ONLY heavy dep — the test skips when the package is absent
(install via ``pip install -e '.[embedding]'``; CI installs the extra).
No network at test time after the model is cached by the HF hub.
"""
from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from processing.embedding.embed import (  # noqa: E402
    HashEmbedding,
    SentenceTransformerEmbedding,
    _reset_default_provider,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_chunk, insert_document  # noqa: E402
from substrate.graph.search import search  # noqa: E402

st = pytest.importorskip("sentence_transformers")  # noqa: F841 — skip if absent

# ─────────────────────────────────────────────────────────────────────
# Fixture corpus: a query whose semantic target and hash target differ.
# ─────────────────────────────────────────────────────────────────────
# Query (personal-finance savings):
QUERY = "how to reduce monthly expenses and save money"
# Semantic TARGET: a paraphrase that shares NO meaningful keyword with the
# query (no "monthly"/"expenses"/"money"/"save"/"reduce"), so a token-bag
# hash embedding cannot surface it on shared vocabulary. ST maps
# "spending"/"reserves" -> "expenses"/"save" by meaning.
TARGET = (
    "cutting household spending to build financial reserves and live "
    "within one's means over the long run"
)
# HASH DISTRACTOR: shares the rare keywords (monthly / expenses / money) but
# is off-topic (corporate accounting, not personal saving). HashEmbedding's
# token-bag cosine is dominated by the shared rare tokens -> distractor is
# hash top-1. ST ranks it low (accounting != personal savings).
DISTRACTOR = (
    "the monthly report tracked money and expenses across every corporate "
    "department for the auditors to review at quarter end"
)
# IRRELEVANT: an unrelated control chunk (should never be top-1 for either).
IRRELEVANT = (
    "the migrating geese flew south as autumn turned the maple leaves red"
)


def _build_corpus(db_path: str, embedder) -> dict[str, str]:
    """Seed 3 docs (one chunk each) with the given embedder's vectors.
    Returns {doc_key: document_id}."""
    doc_specs = [
        ("target", "SemTarget", TARGET),
        ("distractor", "HashDistractor", DISTRACTOR),
        ("irrelevant", "Control", IRRELEVANT),
    ]
    ids: dict[str, str] = {}
    with connect_write(db_path, purpose="divergence-fixture-seed") as con:
        for key, title, text in doc_specs:
            did = f"div-{key}"
            insert_document(
                con, document_id=did, source_tier=4, document_type="article",
                source_uri=f"/div/{key}", title=title,
                investigation_id="divergence-test", raw_text=text,
            )
            insert_chunk(
                con, document_id=did, chunk_index=0, text=text,
                embedding=embedder.encode(text),
            )
            ids[key] = did
    return ids


def _reembed(db_path: str, embedder) -> None:
    """Rewrite every chunk's vector with the given embedder (single writer)."""
    import duckdb

    rows = duckdb.connect(db_path, read_only=True).execute(
        "SELECT chunk_id, text FROM chunks"
    ).fetchall()
    with connect_write(db_path, purpose="divergence-reembed") as con:
        for chunk_id, text in rows:
            con.execute(
                "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
                [list(embedder.encode(text)), chunk_id],
            )


def _top1(db_path: str, embedder, document_ids: list[str]) -> str:
    """Return the top-1 chunk's document_id for QUERY under `embedder`."""
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        res = search(
            con, QUERY, model=embedder, top_k=1, document_ids=document_ids,
            policy_tag="operator_only",  # include all fixture content (§9.0 bypass)
        )
    finally:
        con.close()
    results = res["results"]
    assert results, "search returned no results for the fixture corpus"
    return results[0]["document_id"]


# --------------------------------------------------------------------------
# The divergence proof
# --------------------------------------------------------------------------

def test_hash_top1_differs_from_semantic_top1(tmp_path):
    """Hash retrieval's top-1 must DIFFER from semantic retrieval's top-1 on
    a fixture where the semantic target shares no keywords with the query.

    This is the SPR-02 evidence that selecting SentenceTransformerEmbedding
    changes RESULTS, not just stored vectors. Both providers are exercised
    against the SAME fixture so the only variable is the embedding.
    """
    _reset_default_provider()
    db_path = str(tmp_path / "divergence.duckdb")
    ensure_initialized(db_path)

    hash_model = HashEmbedding()
    st_model = SentenceTransformerEmbedding()

    # 1) Hash-embed the corpus, find hash top-1.
    ids = _build_corpus(db_path, hash_model)
    doc_ids = [ids["target"], ids["distractor"], ids["irrelevant"]]
    hash_top1 = _top1(db_path, hash_model, doc_ids)

    # 2) Re-embed with ST (the real upgrade), find ST top-1.
    _reembed(db_path, st_model)
    semantic_top1 = _top1(db_path, st_model, doc_ids)

    # 3) The divergence: the two providers rank DIFFERENT chunks first.
    assert hash_top1 != semantic_top1, (
        "FAIL: hash and semantic retrieval returned the SAME top-1 — the "
        "provider upgrade did not change results (the failure mode SPR-02 "
        "kills). Either the fixture is too easy or the provider is a no-op."
    )

    # 4) ST returns the SEMANTIC target (the paraphrase); hash does not.
    assert semantic_top1 == ids["target"], (
        f"semantic top-1 was {semantic_top1!r}, expected the paraphrase "
        f"target {ids['target']!r} — ST must surface meaning, not keywords"
    )

    # 5) Hash returned the keyword-sharing distractor (proving the divergence
    # is the documented lexical-collision failure, not chance).
    assert hash_top1 == ids["distractor"], (
        f"hash top-1 was {hash_top1!r}, expected the keyword-sharing "
        f"distractor {ids['distractor']!r} — HashEmbedding should rank on "
        f"shared token overlap"
    )


def test_semantic_neighbours_paraphrase(tmp_path):
    """A stronger semantic property: two paraphrases of the same idea rank
    adjacent under ST regardless of vocabulary, which hash cannot do."""
    _reset_default_provider()
    db_path = str(tmp_path / "paraphrase.duckdb")
    ensure_initialized(db_path)

    q = "physicians treating patients in a hospital"
    para_a = "doctors providing medical care to the sick at a clinic"
    para_b = "medical staff diagnosing illnesses for people seeking treatment"
    unrelated = "a satellite orbited the planet collecting weather data"

    st_model = SentenceTransformerEmbedding()
    specs = [("a", "Pa", para_a), ("b", "Pb", para_b), ("u", "Un", unrelated)]
    ids: dict[str, str] = {}
    with connect_write(db_path, purpose="paraphrase-seed") as con:
        for key, title, text in specs:
            did = f"para-{key}"
            insert_document(
                con, document_id=did, source_tier=4, document_type="article",
                source_uri=f"/para/{key}", title=title,
                investigation_id="paraphrase-test", raw_text=text,
            )
            insert_chunk(
                con, document_id=did, chunk_index=0, text=text,
                embedding=st_model.encode(text),
            )
            ids[key] = did

    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        res = search(
            con, q, model=st_model, top_k=3,
            document_ids=list(ids.values()), policy_tag="operator_only",
        )
    finally:
        con.close()
    ranked = [r["document_id"] for r in res["results"]]
    # The two paraphrases both outrank the unrelated chunk under ST.
    assert ranked.index(ids["u"]) > max(ranked.index(ids["a"]), ranked.index(ids["b"])), (
        f"unrelated chunk did not rank below both paraphrases: {ranked}"
    )
