"""AFF SPR-07 — cross-investigation dedup: link, don't re-store.

The two-polarity, seed-and-catch proof (rigor #3): a dedup that only proves
"duplicates merge" is half a proof — an over-merger passes it while destroying
findings. So BOTH directions are mechanical CI gates here:

  * Polarity A (-k merge)   — a seeded unit + an exact restatement + a
    near-paraphrase, same scope → unit count UNCHANGED, two ``duplicate_of``
    edges, survivor's §9.0 servability unchanged.
  * Polarity B (-k distinct) — a genuinely-distinct-but-similar claim (same
    scope, different vocabulary) → unit count +1, NO ``duplicate_of`` edge; AND
    a similar claim in a DIFFERENT scope → +1, no edge (the scope guard). The
    threshold is proven NUMERICALLY to sit strictly between the duplicate-pair
    cosine and the distinct-pair cosine (not eyeballed).
  * dedup-rate (-k rate)    — the M5 metric equals the seeded expectation
    (2 merges / 3 attempts), read both from the deposit-time counter and from
    the corpus-audit sibling, which must agree.

Embedding is pinned to the deterministic ``HashEmbedding`` (a token-BAG) so the
gates are reproducible and do NOT need ``sentence-transformers`` installed.

HONESTY (rigor #1) — what these tests do NOT cover: the hash embedder is a pure
token bag, so a one-word ANTONYM flip ("X increases Y" vs "X decreases Y")
scores the SAME cosine as the matching paraphrase — cosine cannot see negation.
Polarity B therefore uses a distinct pair with genuinely different VOCABULARY
(provably below threshold) to prove the threshold guard, and a cross-scope case
to prove the scope guard. The same-scope-antonym residual is documented in the
module docstring + the handoff; it is NOT claimed solved here.
"""

from __future__ import annotations

import os

import pytest

from interfaces.research.api.cross_doc import _cosine
from processing.embedding import (
    HashEmbedding,
    _reset_default_provider,
    set_default_embedding_provider,
)
from runtime.db_lock import connect_write
from substrate.corpus_audit import CHECK_DEDUP_RATE, run_audit, unit_dedup_rate
from substrate.graph import insight_question as iq
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.ops import insert_node
from substrate.graph.schema import init_database
from substrate.schemas.events import GraphEdgeInsertedPayload, GraphNodeInsertedPayload
from substrate.unit_dedup import (
    UNIT_DEDUP_COSINE_THRESHOLD,
    CandidateUnit,
    DedupRate,
    ExistingUnit,
    find_near_duplicate,
)

# ---------------------------------------------------------------------------
# Seeded claim texts — one duplicate cluster, one genuinely-distinct claim.
# ---------------------------------------------------------------------------

SEED = "neutral atom qubits reached a sub one percent two qubit gate error rate"
EXACT = SEED  # a literal restatement
PARAPHRASE = SEED + " at scale"  # near-paraphrase, heavy token overlap
# Distinct-but-similar: SAME research domain, GENUINELY different assertion AND
# different vocabulary, so its token-bag cosine to SEED is far below threshold.
DISTINCT = "trapped ion processors demonstrate longer coherence but slower entangling operations"


@pytest.fixture(autouse=True)
def _hash_embeddings():
    """Pin a deterministic token-bag embedder for every test (no
    sentence-transformers dependency; reproducible cosines)."""
    set_default_embedding_provider(HashEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def emb():
    return HashEmbedding()


@pytest.fixture
def graph_env(monkeypatch, tmp_path):
    """Temp graph DB + isolated event dir, with the promotion path's default db
    pointed at the temp DB so the con=None path never touches prod."""
    db_path = os.path.join(tmp_path, "graph.duckdb")
    events_dir = os.path.join(tmp_path, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    con = connect_write(db_path, purpose="spr07_init")
    try:
        init_database(con)
    finally:
        con.close()
    return db_path


def _seed_grounding(con, emb, *, doc_id="doc1", chunk_id="ch1", content_class="public_domain"):
    """A document + chunk + claim node so a deposited unit is grounded (the
    deposit contract requires source_document_id + chunk_id)."""
    con.execute(
        "INSERT INTO documents (document_id, title, source_tier, document_type, content_class) "
        "VALUES (?, ?, 1, 'paper', ?)",
        [doc_id, "T", content_class],
    )
    con.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding, token_count) "
        "VALUES (?, ?, 0, 'x', ?, 1)",
        [chunk_id, doc_id, emb.encode("x")],
    )
    return insert_node(
        con, canonical_label="claim", node_type="claim", graph_scope="depth",
        investigation_id="inv-seed", embedding=emb.encode("claim"), on_conflict="ignore",
    )


def _count_units(con, node_type="insight"):
    return con.execute(
        "SELECT COUNT(*) FROM nodes WHERE node_type = ?", [node_type]
    ).fetchone()[0]


def _count_dup_edges(con):
    return con.execute(
        "SELECT COUNT(*) FROM edges WHERE relation = 'duplicate_of'"
    ).fetchone()[0]


# ===========================================================================
# Threshold calibration proof (rigor #3) — the threshold sits STRICTLY between
# the distinct-pair cosine and the duplicate-pair cosine. Verified NUMERICALLY.
# ===========================================================================


def test_threshold_sits_strictly_between_distinct_and_duplicate_cosines(emb):
    dup_cos = _cosine(emb.encode(SEED), emb.encode(PARAPHRASE))
    distinct_cos = _cosine(emb.encode(SEED), emb.encode(DISTINCT))
    # The whole proof: distinct < threshold < duplicate, with strict gaps.
    assert distinct_cos < UNIT_DEDUP_COSINE_THRESHOLD < dup_cos, (
        f"threshold {UNIT_DEDUP_COSINE_THRESHOLD} must sit strictly between "
        f"distinct cosine {distinct_cos:.4f} and duplicate cosine {dup_cos:.4f}"
    )
    # And the exact restatement is the maximal duplicate signal.
    assert _cosine(emb.encode(SEED), emb.encode(EXACT)) == pytest.approx(1.0)


# ===========================================================================
# M2 — find_near_duplicate is PURE and behaves per tier.
# ===========================================================================


def test_m2_pure_tier1_exact_retrieval_key(emb):
    c = CandidateUnit(text="anything", retrieval_key="node-X", investigation_id="inv-1")
    e = ExistingUnit(unit_id="node-X", text="totally different words here",
                     retrieval_key="node-X", investigation_id="inv-1")
    m = find_near_duplicate(c, [e], embedding_provider=emb)
    assert m is not None and m.tier == 1 and m.key_type == "retrieval_key"
    assert m.existing_unit_id == "node-X"


def test_m2_pure_tier2_near_dup_same_scope(emb):
    c = CandidateUnit(text=PARAPHRASE, retrieval_key="node-c", investigation_id="inv-1")
    e = ExistingUnit(unit_id="node-s", text=SEED, retrieval_key="node-s", investigation_id="inv-1")
    m = find_near_duplicate(c, [e], embedding_provider=emb)
    assert m is not None and m.tier == 2 and m.key_type == "embedding"
    assert m.cosine >= UNIT_DEDUP_COSINE_THRESHOLD


def test_m2_scope_guard_cosine_alone_never_merges_across_scopes(emb):
    """The false-merge guard: an identical-vocabulary claim in a DIFFERENT
    investigation AND a different document is NOT a duplicate."""
    c = CandidateUnit(text=SEED, retrieval_key="node-c", investigation_id="inv-A",
                      source_document_id="docA")
    e = ExistingUnit(unit_id="node-s", text=SEED, retrieval_key="node-s",
                     investigation_id="inv-B", source_document_id="docB")
    assert find_near_duplicate(c, [e], embedding_provider=emb) is None


def test_m2_distinct_below_threshold_same_scope_no_match(emb):
    c = CandidateUnit(text=DISTINCT, retrieval_key="node-c", investigation_id="inv-1")
    e = ExistingUnit(unit_id="node-s", text=SEED, retrieval_key="node-s", investigation_id="inv-1")
    assert find_near_duplicate(c, [e], embedding_provider=emb) is None


def test_m2_low_confidence_identity_never_tier1_merges(emb):
    """A LOW-confidence identity (title+author/ref fallback) NEVER triggers a
    Tier-1 merge — inherits substrate.dedup's LOW-never-merges rule."""
    from substrate.dedup import IdentityRecord
    # Two records with only a title => LOW-confidence keys; even identical
    # titles must not Tier-1 merge (and distinct text keeps Tier 2 silent too).
    rec = IdentityRecord(ref_id="r1", source="s", title="History", author="Anonymous")
    c = CandidateUnit(text="alpha beta gamma", retrieval_key="node-c",
                      investigation_id="inv-1", identity_record=rec)
    e = ExistingUnit(unit_id="node-s", text="delta epsilon zeta",
                     retrieval_key="node-s", investigation_id="inv-1",
                     identity_record=IdentityRecord(ref_id="r2", source="s2",
                                                    title="History", author="Anonymous"))
    m = find_near_duplicate(c, [e], embedding_provider=emb)
    # No Tier-1 (LOW key) and no Tier-2 (distinct text below threshold).
    assert m is None


def test_m2_high_confidence_identity_tier1_merges(emb):
    """Two units carrying the SAME high-confidence stable id (a DOI) Tier-1
    merge even with different phrasing."""
    from substrate.dedup import IdentityRecord
    doi = "10.1/abc"
    c = CandidateUnit(text="phrasing one", retrieval_key="node-c", investigation_id="inv-1",
                      identity_record=IdentityRecord(ref_id="r1", source="s", doi=doi))
    e = ExistingUnit(unit_id="node-s", text="completely other phrasing", retrieval_key="node-s",
                     investigation_id="inv-1",
                     identity_record=IdentityRecord(ref_id="r2", source="s2", doi=doi))
    m = find_near_duplicate(c, [e], embedding_provider=emb)
    assert m is not None and m.tier == 1 and m.key_type == "doi"


# ===========================================================================
# Polarity A (-k merge) — duplicate is LINKED, not stored.
# ===========================================================================


def test_merge_polarity_a_duplicate_is_linked_not_stored(graph_env, emb):
    con = connect_write(graph_env, purpose="spr07_merge")
    try:
        con.execute("BEGIN")
        claim = _seed_grounding(con, emb)
        rate = DedupRate()
        kw = dict(investigation_id="inv-1", confidence="high", supported_by=[claim],
                  source_document_id="doc1", chunk_id="ch1", embedding_provider=emb,
                  con=con, dedup=True, dedup_rate=rate)
        n1 = promote_insight(text=SEED, **kw)
        n2 = promote_insight(text=EXACT, **kw)         # exact restatement -> link
        n3 = promote_insight(text=PARAPHRASE, **kw)    # near-paraphrase   -> link
        con.execute("COMMIT")

        # Unit count UNCHANGED (one survivor), all deposits resolve to it.
        assert _count_units(con, "insight") == 1
        assert n1 == n2 == n3
        # Two duplicate_of edges (one per linked deposit).
        assert _count_dup_edges(con) == 2
        # Rate = 2 merges / 3 attempts.
        assert rate.linked == 2 and rate.attempts == 3
    finally:
        con.close()


def test_question_dedup_routes_duplicate_link_through_event_sink(graph_env, emb):
    payloads = []
    con = connect_write(graph_env, purpose="spr07_question_sink")
    try:
        survivor = promote_question(
            text=SEED, investigation_id="inv-1", embedding_provider=emb,
            con=con, dedup=True, event_sink=payloads.append,
        )
        assert [type(payload) for payload in payloads] == [GraphNodeInsertedPayload]
        payloads.clear()

        resolved = promote_question(
            text=PARAPHRASE, investigation_id="inv-1", embedding_provider=emb,
            con=con, dedup=True, event_sink=payloads.append,
        )
        assert resolved == survivor
        assert [type(payload) for payload in payloads] == [GraphEdgeInsertedPayload]
        assert payloads[0].relation == "duplicate_of"
    finally:
        con.close()


def test_merge_polarity_a_survivor_servability_unchanged(graph_env, emb):
    """§9.0-safe: a duplicate_of link NEVER widens the survivor's servability.

    The survivor's node row is the only carrier of servability-relevant state;
    a link writes an edge, never touches the row. We assert the survivor's row
    (node + its grounding) is byte-identical before and after the merge."""
    con = connect_write(graph_env, purpose="spr07_serv")
    try:
        con.execute("BEGIN")
        claim = _seed_grounding(con, emb)
        kw = dict(investigation_id="inv-1", confidence="high", supported_by=[claim],
                  source_document_id="doc1", chunk_id="ch1", embedding_provider=emb,
                  con=con, dedup=True)
        survivor = promote_insight(text=SEED, **kw)
        before = con.execute(
            "SELECT node_type, canonical_label, metadata, graph_scope FROM nodes WHERE node_id = ?",
            [survivor],
        ).fetchone()
        # A near-paraphrase deposit links to the survivor.
        promote_insight(text=PARAPHRASE, **kw)
        con.execute("COMMIT")
        after = con.execute(
            "SELECT node_type, canonical_label, metadata, graph_scope FROM nodes WHERE node_id = ?",
            [survivor],
        ).fetchone()
        assert before == after, "a duplicate_of link must not mutate the survivor row"
        # And the survivor is still the only insight row.
        assert _count_units(con, "insight") == 1
    finally:
        con.close()


def test_merge_polarity_a_questions_dedup_too(graph_env, emb):
    """The question deposit path links near-dup questions the same way."""
    con = connect_write(graph_env, purpose="spr07_q")
    try:
        con.execute("BEGIN")
        _seed_grounding(con, emb)
        kw = dict(investigation_id="inv-1", source_document_id="doc1", chunk_id="ch1",
                  embedding_provider=emb, con=con, dedup=True)
        q1 = promote_question(text=SEED, **kw)
        q2 = promote_question(text=PARAPHRASE, **kw)
        con.execute("COMMIT")
        assert q1 == q2
        assert _count_units(con, "question") == 1
        assert _count_dup_edges(con) == 1
    finally:
        con.close()


# ===========================================================================
# Polarity B (-k distinct) — distinct-but-similar is PRESERVED (non-vacuity).
# ===========================================================================


def test_distinct_polarity_b_similar_but_different_is_preserved(graph_env, emb):
    con = connect_write(graph_env, purpose="spr07_distinct")
    try:
        con.execute("BEGIN")
        claim = _seed_grounding(con, emb)
        kw = dict(investigation_id="inv-1", confidence="high", supported_by=[claim],
                  source_document_id="doc1", chunk_id="ch1", embedding_provider=emb,
                  con=con, dedup=True)
        promote_insight(text=SEED, **kw)
        before = _count_units(con, "insight")
        # A genuinely-distinct claim in the SAME scope (below threshold) is
        # INSERTED, not linked.
        nid = promote_insight(text=DISTINCT, **kw)
        con.execute("COMMIT")
        assert _count_units(con, "insight") == before + 1, "distinct claim must be a new unit"
        # No duplicate_of edge was created for the distinct deposit.
        assert _count_dup_edges(con) == 0
        # The distinct unit got its own (content-addressed) node id.
        assert isinstance(nid, str) and nid.startswith("insight-")
    finally:
        con.close()


def test_distinct_polarity_b_similar_in_different_scope_is_preserved(graph_env, emb):
    """The Tier-2 scope guard at the deposit layer: a near-PARAPHRASE (different
    text, so a different content-addressed node id — no Tier-1 retrieval-key
    match — but cosine ABOVE threshold) deposited in a DIFFERENT investigation
    and a different document is a NEW unit, not a link. Cosine alone never
    merges across unrelated scopes.

    (Note: identical TEXT would content-address to the SAME node id and link via
    Tier 1 — that is the scope-INDEPENDENT 'one entity everywhere' identity, not
    a cosine merge. The scope guard governs the Tier-2 cosine path, which is
    what this test exercises.)"""
    con = connect_write(graph_env, purpose="spr07_scope")
    try:
        con.execute("BEGIN")
        claim1 = _seed_grounding(con, emb, doc_id="docA", chunk_id="chA")
        claim2 = _seed_grounding(con, emb, doc_id="docB", chunk_id="chB")
        promote_insight(text=SEED, investigation_id="inv-A", confidence="high",
                        supported_by=[claim1], source_document_id="docA", chunk_id="chA",
                        embedding_provider=emb, con=con, dedup=True)
        before = _count_units(con, "insight")
        # Near-paraphrase (cosine >= threshold) but DIFFERENT scope => no merge.
        assert _cosine(emb.encode(SEED), emb.encode(PARAPHRASE)) >= UNIT_DEDUP_COSINE_THRESHOLD
        promote_insight(text=PARAPHRASE, investigation_id="inv-B", confidence="high",
                        supported_by=[claim2], source_document_id="docB", chunk_id="chB",
                        embedding_provider=emb, con=con, dedup=True)
        con.execute("COMMIT")
        assert _count_units(con, "insight") == before + 1
        assert _count_dup_edges(con) == 0
    finally:
        con.close()


# ===========================================================================
# M5 (-k rate) — dedup-rate metric equals the seeded expectation.
# ===========================================================================


def test_rate_metric_equals_seeded_expectation_counter_and_audit_agree(graph_env, emb):
    con = connect_write(graph_env, purpose="spr07_rate")
    try:
        con.execute("BEGIN")
        claim = _seed_grounding(con, emb)
        rate = DedupRate()
        kw = dict(investigation_id="inv-1", confidence="high", supported_by=[claim],
                  source_document_id="doc1", chunk_id="ch1", embedding_provider=emb,
                  con=con, dedup=True, dedup_rate=rate)
        promote_insight(text=SEED, **kw)        # insert (attempt 1, not linked)
        promote_insight(text=EXACT, **kw)       # link   (attempt 2, linked)
        promote_insight(text=PARAPHRASE, **kw)  # link   (attempt 3, linked)
        con.execute("COMMIT")

        # Deposit-time counter: 2 merges / 3 attempts.
        assert (rate.linked, rate.attempts) == (2, 3)
        assert rate.rate == pytest.approx(2 / 3)

        # Corpus-audit sibling reads the SAME truth off the graph and agrees:
        # 1 unit + 2 duplicate_of edges => 2 linked / 3 attempts.
        linked, attempts, audit_rate = unit_dedup_rate(con)
        assert (linked, attempts) == (2, 3)
        assert audit_rate == pytest.approx(rate.rate)
    finally:
        con.close()


def test_rate_metric_surfaced_through_run_audit(graph_env, emb):
    """The metric is queryable by one command (run_audit), as a sibling check
    that is a MEASURE (always ok=True), not a gate."""
    con = connect_write(graph_env, purpose="spr07_audit_seed")
    try:
        con.execute("BEGIN")
        claim = _seed_grounding(con, emb)
        kw = dict(investigation_id="inv-1", confidence="high", supported_by=[claim],
                  source_document_id="doc1", chunk_id="ch1", embedding_provider=emb,
                  con=con, dedup=True)
        promote_insight(text=SEED, **kw)
        promote_insight(text=PARAPHRASE, **kw)
        con.execute("COMMIT")
    finally:
        con.close()
    # include_binding=False: the static connector binding is unrelated here.
    result = run_audit(graph_env, include_binding=False)
    measure = result.check(CHECK_DEDUP_RATE)
    assert measure.ok is True  # informational measure, never fails the audit
    assert "1/2" in measure.detail and "0.500" in measure.detail


def test_rate_zero_when_no_deposits(graph_env):
    con = connect_write(graph_env, purpose="spr07_empty_rate")
    try:
        linked, attempts, rate = unit_dedup_rate(con)
        assert (linked, attempts, rate) == (0, 0, 0.0)
    finally:
        con.close()
