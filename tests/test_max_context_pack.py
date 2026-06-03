"""DRW SPR-04 — maximum-context pack (insight/question injection).

Mechanical gates: scoped retrieval (ranked, embedding-less fallback);
deterministic budgeting; highest-ranked never dropped; flagged assembler
integration; accurate coverage reporting.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.context_pack.assembler import LayerSource
from substrate.context_pack.note_budget import score_note, select_within_budget
from substrate.context_pack.note_injection import (
    NOTES_LAYER_SOURCE,
    assemble_context_pack_with_notes,
    build_project_notes_layer,
)
from substrate.context_pack.note_retrieval import RetrievedNote, retrieve_project_notes
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 16

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def graph(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return db


def _seed(db, n_insights, n_questions=0, provider=None):
    provider = provider or _FakeEmbedding()
    con = connect_write(db, purpose="seed")
    try:
        con.execute("BEGIN")
        for i in range(n_insights):
            promote_insight(text=f"Insight {i} about subject {i}.", investigation_id="inv-1",
                            confidence="high" if i % 2 == 0 else "low",
                            embedding_provider=provider, con=con)
        for i in range(n_questions):
            promote_question(text=f"Open question {i}?", investigation_id="inv-1",
                             embedding_provider=provider, con=con)
        con.execute("COMMIT")
    finally:
        con.close()


# --------------------------------------------------------------------------
# M1 — retrieval
# --------------------------------------------------------------------------


def test_retrieval_returns_ranked_notes(graph):
    _seed(graph, n_insights=5, n_questions=2)
    con = connect_read(graph)
    try:
        notes = retrieve_project_notes(con, task_text="subject 3",
                                       embedding_provider=_FakeEmbedding())
    finally:
        con.close()
    assert len(notes) == 7
    assert {n.node_type for n in notes} == {"insight", "question"}
    # Ranked by similarity descending.
    sims = [n.similarity for n in notes if n.has_embedding]
    assert sims == sorted(sims, reverse=True)


def test_retrieval_embeddingless_fallback(graph):
    # Manually insert an embedding-less insight (shouldn't happen post-SPR-01).
    con = connect_write(graph, purpose="seed")
    try:
        con.execute("INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                    "VALUES ('node-noemb','no embedding insight','insight','depth')")
    finally:
        con.close()
    con = connect_read(graph)
    try:
        notes = retrieve_project_notes(con, task_text="anything", embedding_provider=_FakeEmbedding())
    finally:
        con.close()
    assert any(not n.has_embedding and n.node_id == "node-noemb" for n in notes)


# --------------------------------------------------------------------------
# M2 — budgeting determinism + no high-value drop
# --------------------------------------------------------------------------


def _mk(node_id, sim, conf="moderate"):
    return RetrievedNote(node_id=node_id, node_type="insight",
                         text=f"text for {node_id} " + "x" * 40, similarity=sim,
                         confidence=conf, created_at=f"2026-05-{int(node_id[-2:]):02d}",
                         has_embedding=True)


def test_budget_is_deterministic():
    notes = [_mk(f"n-{i:02d}", sim=(50 - i) / 50.0) for i in range(50)]
    a, ca = select_within_budget(notes, token_budget=200)
    b, cb = select_within_budget(notes, token_budget=200)
    assert [n.node_id for n in a] == [n.node_id for n in b]   # identical selection
    assert ca == cb


def test_budget_never_drops_highest_ranked():
    notes = [_mk(f"n-{i:02d}", sim=(50 - i) / 50.0) for i in range(50)]
    selected, coverage = select_within_budget(notes, token_budget=120)
    assert coverage.truncated > 0                              # genuinely over budget
    selected_ids = {n.node_id for n in selected}
    # The single highest-scored note must be present.
    top = max(notes, key=lambda n: (score_note(n, 1.0), n.node_id))
    assert max(notes, key=lambda n: score_note(n, 0.5)).node_id  # smoke
    # The top-similarity note (n-00) is highest-ranked → must survive.
    assert "n-00" in selected_ids


# --------------------------------------------------------------------------
# M3 — flagged assembler integration
# --------------------------------------------------------------------------


def test_injection_flag_changes_pack(graph):
    _seed(graph, n_insights=4)
    con = connect_read(graph)
    try:
        base_layers = [LayerSource(kind="session", source="task", content="do the thing")]
        on = assemble_context_pack_with_notes(
            role="note_taker", investigation_id="inv-1", layers=base_layers, con=con,
            task_text="subject 2", embedding_provider=_FakeEmbedding(),
            include_project_notes=True,
        )
        off = assemble_context_pack_with_notes(
            role="note_taker", investigation_id="inv-1", layers=base_layers, con=con,
            task_text="subject 2", embedding_provider=_FakeEmbedding(),
            include_project_notes=False,
        )
    finally:
        con.close()
    assert on.notes_injected and not off.notes_injected
    assert NOTES_LAYER_SOURCE in on.pack.text
    assert NOTES_LAYER_SOURCE not in off.pack.text
    assert on.pack.text != off.pack.text


# --------------------------------------------------------------------------
# M4 — coverage reporting accuracy
# --------------------------------------------------------------------------


def test_coverage_accurate(graph):
    _seed(graph, n_insights=10)
    con = connect_read(graph)
    try:
        # Tiny budget forces truncation; coverage must reflect it.
        layer, coverage = build_project_notes_layer(
            con, task_text="subject 1", embedding_provider=_FakeEmbedding(),
            token_budget=60,
        )
    finally:
        con.close()
    assert coverage.relevant == 10
    assert coverage.included < coverage.relevant
    assert coverage.truncated == coverage.relevant - coverage.included
    assert not coverage.fully_covered


def test_coverage_full_when_budget_ample(graph):
    _seed(graph, n_insights=3)
    con = connect_read(graph)
    try:
        layer, coverage = build_project_notes_layer(
            con, task_text="subject 1", embedding_provider=_FakeEmbedding(),
            token_budget=100_000,
        )
    finally:
        con.close()
    assert coverage.relevant == 3 and coverage.included == 3 and coverage.fully_covered
