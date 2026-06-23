"""DRW SPR-07 — structural gap detection.

Mechanical gates: the three detectors; computed ranking; the grounding guard
(a candidate is impossible without backing node ids); determinism; empty
graph; and the SPR-05 plan_from_gap integration.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.gap_detection import (
    GapCandidate,
    UngroundedGapError,
    detect_gaps,
    find_contradictions,
    find_unanswered_questions,
    find_unsupported_claims,
)
from substrate.gap_detection.contradiction import negation_verifier
from substrate.graph import ops
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.schema import init_database_at_path


class _ConstEmbedding:
    """Returns the SAME vector for every text — so all nodes are maximally
    similar, isolating the contradiction *verifier* from embedding noise."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.5] * self.dimension


class _HashEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_HashEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def db(monkeypatch):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: path)
    init_database_at_path(path)
    return path


# --------------------------------------------------------------------------
# M1 — unanswered questions
# --------------------------------------------------------------------------


def test_unanswered_question_detected(db):
    con = connect_write(db, purpose="seed")
    try:
        q_open = promote_question(text="What is the moat?", investigation_id="inv-1", con=con)
        q_answered = promote_question(text="What is revenue?", investigation_id="inv-1", con=con)
        ins = promote_insight(text="Revenue is $5M.", investigation_id="inv-1", con=con)
        # Resolve the second question with a confident resolved_by edge.
        ops.insert_edge(con, source_node_id=q_answered, target_node_id=ins,
                        relation="resolved_by", source_tier=2, extraction_confidence=0.9,
                        graph_scope="depth", investigation_id="inv-1", on_conflict="ignore")
    finally:
        con.close()
    con = connect_read(db)
    try:
        open_qs = {q.node_id for q in find_unanswered_questions(con)}
    finally:
        con.close()
    assert q_open in open_qs and q_answered not in open_qs


# --------------------------------------------------------------------------
# M2 — unsupported claims
# --------------------------------------------------------------------------


def test_unsupported_claim_detected(db):
    con = connect_write(db, purpose="seed")
    try:
        # A claim node with no evidence edge → unsupported.
        unsupported = ops.insert_node(con, canonical_label="Acme will IPO in 2027",
                                      node_type="claim", graph_scope="depth", investigation_id="inv-1")
        # A claim with a chunk-backed evidence edge → supported.
        supported = ops.insert_node(con, canonical_label="Acme raised $5M",
                                    node_type="claim", graph_scope="depth", investigation_id="inv-1")
        other = ops.insert_node(con, canonical_label="Acme", node_type="organization",
                                graph_scope="depth", investigation_id="inv-1")
        con.execute("INSERT INTO documents (document_id, source_tier, document_type) VALUES ('d1', 2, 'report')")
        con.execute("INSERT INTO chunks (chunk_id, document_id, chunk_index, text) VALUES ('c1','d1',0,'...')")
        ops.insert_edge(con, source_node_id=supported, target_node_id=other, relation="reports",
                        source_tier=2, extraction_confidence=0.8, graph_scope="depth",
                        investigation_id="inv-1", chunk_id="c1", source_document_id="d1")
    finally:
        con.close()
    con = connect_read(db)
    try:
        unsupp = {c.node_id for c in find_unsupported_claims(con)}
    finally:
        con.close()
    assert unsupported in unsupp and supported not in unsupp


# --------------------------------------------------------------------------
# M3 — contradictions (precision)
# --------------------------------------------------------------------------


def test_contradiction_precision(db, monkeypatch):
    # All nodes share an embedding (const) → similarity isolates the verifier.
    monkeypatch.setattr("processing.embedding.embed._DEFAULT_PROVIDER", _ConstEmbedding(), raising=False)
    const = _ConstEmbedding()
    con = connect_write(db, purpose="seed")
    try:
        promote_insight(text="Margins are healthy.", investigation_id="inv-1",
                        embedding_provider=const, con=con)
        promote_insight(text="Margins are not healthy.", investigation_id="inv-1",
                        embedding_provider=const, con=con)
        promote_insight(text="Margins are strong.", investigation_id="inv-1",
                        embedding_provider=const, con=con)
    finally:
        con.close()
    con = connect_read(db)
    try:
        contras = find_contradictions(con, verifier=negation_verifier)
    finally:
        con.close()
    # The negated pair is flagged; the two non-negated agreeing statements are not.
    texts = {frozenset((c.text_a, c.text_b)) for c in contras}
    assert frozenset(("Margins are healthy.", "Margins are not healthy.")) in texts
    assert frozenset(("Margins are healthy.", "Margins are strong.")) not in texts


# --------------------------------------------------------------------------
# M6 — the grounding guard (anti-free-association)
# --------------------------------------------------------------------------


def test_gap_candidate_requires_backing_nodes():
    with pytest.raises(UngroundedGapError):
        GapCandidate(kind="unanswered_question", question="anything?", backing_node_ids=())
    with pytest.raises(UngroundedGapError):
        GapCandidate(kind="unanswered_question", question="anything?", backing_node_ids=("",))
    ok = GapCandidate(kind="unanswered_question", question="real?", backing_node_ids=("node-1",))
    assert ok.node_id == "node-1" and ok.gap_id.startswith("gap-")


def test_every_candidate_is_grounded(db):
    con = connect_write(db, purpose="seed")
    try:
        promote_question(text="Unanswered?", investigation_id="inv-1", con=con)
        ops.insert_node(con, canonical_label="Unsupported claim", node_type="claim",
                        graph_scope="depth", investigation_id="inv-1")
    finally:
        con.close()
    con = connect_read(db)
    try:
        gaps = detect_gaps(con)
    finally:
        con.close()
    assert gaps
    for g in gaps:
        assert g.backing_node_ids  # impossible to be empty by construction


# --------------------------------------------------------------------------
# determinism + empty graph
# --------------------------------------------------------------------------


def test_detection_is_deterministic(db):
    con = connect_write(db, purpose="seed")
    try:
        for i in range(5):
            promote_question(text=f"Open question {i}?", investigation_id="inv-1", con=con)
    finally:
        con.close()
    con = connect_read(db)
    try:
        a = detect_gaps(con)
        b = detect_gaps(con)
    finally:
        con.close()
    assert [(g.gap_id, g.impact_score) for g in a] == [(g.gap_id, g.impact_score) for g in b]


def test_empty_graph_returns_no_gaps(db):
    con = connect_read(db)
    try:
        assert detect_gaps(con) == []
    finally:
        con.close()


# --------------------------------------------------------------------------
# SPR-05 integration — a candidate is a valid plan_from_gap seed
# --------------------------------------------------------------------------


def test_candidate_feeds_cascade_planner_seed(db):
    from roles.cascade_planner import SubQuestion, plan_from_gap

    class _Dec:
        def decompose(self, q, *, context=""):
            return [SubQuestion(question="sub a"), SubQuestion(question="sub b")]

    con = connect_write(db, purpose="seed")
    try:
        promote_question(text="What drives churn?", investigation_id="inv-1", con=con)
    finally:
        con.close()
    con = connect_read(db)
    try:
        gaps = detect_gaps(con)
    finally:
        con.close()
    report = plan_from_gap(gaps[0], decomposer=_Dec())
    assert report.tree.seed_kind == "gap"
    assert report.tree.seed_provenance["gap_id"] == gaps[0].gap_id
