"""DRW SPR-03 — always-on note-taking + living notes.

Mechanical gates: document pass promotes provenance-carrying nodes; step
pass dedupes within a run; living-note updates are deterministic by event
seq under concurrent challenge + background edit; unresolvable challenge
escalates (without launching); idempotent re-runs promote zero; scheduler
debounces + applies budget backpressure.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from roles.note_taker import (
    AsyncNoteScheduler,
    Distillation,
    DistilledQuestion,
    RunNoteDeduper,
    apply_refinement,
    challenge_note,
    notes_for_step,
    run_document_pass,
)
from roles.note_taker.parser import ExtractedNote
from substrate.graph.schema import init_database_at_path
from substrate.graph.insight_question import insight_node_id, promote_insight
from runtime.db_lock import connect_read, connect_write
from substrate.event_log import trajectory
from substrate.schemas.events import ActionType
from processing.embedding import set_default_embedding_provider, _reset_default_provider


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class FakeDistiller:
    """Deterministic distiller: returns the insights/questions it was seeded
    with, ignoring the text. Lets us test the machinery without an LLM."""

    def __init__(self, insights=(), questions=()):
        self._insights = list(insights)
        self._questions = list(questions)

    def distill(self, text, *, source_event_ids=(), context=""):
        notes = [ExtractedNote(note_id=f"n-{i}", text=t, confidence="moderate",
                               source_event_ids=tuple(source_event_ids) or ("ev-0",))
                 for i, t in enumerate(self._insights)]
        qs = [DistilledQuestion(text=q) for q in self._questions]
        return Distillation(insights=notes, questions=qs)


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "graph.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    import roles.note_taker.living_note as ln
    monkeypatch.setattr(ln, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev}


# --------------------------------------------------------------------------
# M1 — document pass
# --------------------------------------------------------------------------


async def test_document_pass_promotes_with_provenance(env):
    distiller = FakeDistiller(insights=["GPUs gate scale.", "Capital is abundant."],
                              questions=["What is the moat?"])
    res = await run_document_pass(
        "doc-1", "long source text", investigation_id="inv-1",
        distiller=distiller, chunk_ids=["c1", "c2"], events_dir=env["events"],
    )
    assert len(res.insight_node_ids) == 2 and len(res.question_node_ids) == 1
    con = connect_read(env["db"])
    try:
        # Every insight node records source-document provenance (no
        # provenance-free notes).
        import json
        for nid in res.insight_node_ids:
            meta = json.loads(con.execute("SELECT metadata FROM nodes WHERE node_id=?", [nid]).fetchone()[0])
            assert meta.get("source_chunk_ids") == ["c1", "c2"]
        # note.emerged + question.identified emitted to the trajectory.
        actions = {r["action_type"] for r in trajectory("inv-1", events_dir=env["events"])}
        assert ActionType.NOTE_EMERGED.value in actions
        assert ActionType.QUESTION_IDENTIFIED.value in actions
    finally:
        con.close()


async def test_document_pass_idempotent(env):
    distiller = FakeDistiller(insights=["GPUs gate scale."])
    await run_document_pass("doc-1", "t", investigation_id="inv-1",
                            distiller=distiller, chunk_ids=["c1"], events_dir=env["events"])
    await run_document_pass("doc-1", "t", investigation_id="inv-1",
                            distiller=distiller, chunk_ids=["c1"], events_dir=env["events"])
    con = connect_read(env["db"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
    finally:
        con.close()


# --------------------------------------------------------------------------
# M2 — step pass within-run dedup
# --------------------------------------------------------------------------


def test_step_pass_dedupes_within_run(env):
    deduper = RunNoteDeduper()
    distiller = FakeDistiller(insights=["Same insight."])
    a = notes_for_step("inv-1", "step text 1", distiller=distiller, deduper=deduper)
    b = notes_for_step("inv-1", "step text 2 restating it", distiller=distiller, deduper=deduper)
    assert len(a) == 1 and a[0].kind == "note"
    assert b == []                       # restated insight suppressed within the run


# --------------------------------------------------------------------------
# M3 — living-note determinism (the load-bearing case)
# --------------------------------------------------------------------------


async def test_living_note_updates_in_place_no_duplicate(env):
    nid = promote_insight(text="Initial claim.", investigation_id="inv-1")
    r = apply_refinement(nid, "Refined claim.", seq=5, investigation_id="inv-1",
                         document_id="doc-1", events_dir=env["events"])
    assert r.applied is True
    con = connect_read(env["db"])
    try:
        # Same node, new text; no duplicate node created.
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
        assert con.execute("SELECT canonical_label FROM nodes WHERE node_id=?", [nid]).fetchone()[0] == "Refined claim."
    finally:
        con.close()


async def test_living_note_seq_rule_is_deterministic(env):
    # seq 12 wins over seq 11 regardless of arrival order; loser preserved in log.
    nid = promote_insight(text="Base.", investigation_id="inv-1")
    # Apply higher seq FIRST, then the lower seq (out of order).
    apply_refinement(nid, "from-seq-12", seq=12, investigation_id="inv-1", document_id="doc-1", events_dir=env["events"])
    loser = apply_refinement(nid, "from-seq-11", seq=11, investigation_id="inv-1", document_id="doc-1", events_dir=env["events"])
    assert loser.applied is False and loser.superseded is True
    con = connect_read(env["db"])
    try:
        assert con.execute("SELECT canonical_label FROM nodes WHERE node_id=?", [nid]).fetchone()[0] == "from-seq-12"
    finally:
        con.close()
    # Both refinements recorded in the log (history preserved).
    refines = [r for r in trajectory("inv-1", events_dir=env["events"])
               if r["action_type"] == ActionType.NOTE_REFINED.value]
    assert len(refines) == 2
    assert any(r["payload"]["new_text"] == "from-seq-11" for r in refines)


# --------------------------------------------------------------------------
# M6 — challenge → escalation seam (no launch)
# --------------------------------------------------------------------------


async def test_resolvable_challenge_refines(env):
    nid = promote_insight(text="Acme is small.", investigation_id="inv-1")
    r = challenge_note(nid, "Actually it has 500 staff", resolver=lambda cur, ch: "Acme is mid-sized.",
                       seq=3, investigation_id="inv-1", document_id="doc-1", events_dir=env["events"])
    assert r.applied and not r.escalated
    con = connect_read(env["db"])
    try:
        assert con.execute("SELECT canonical_label FROM nodes WHERE node_id=?", [nid]).fetchone()[0] == "Acme is mid-sized."
    finally:
        con.close()


async def test_unresolvable_challenge_escalates_without_launch(env):
    nid = promote_insight(text="Margins are healthy.", investigation_id="inv-1")
    r = challenge_note(nid, "Source for margins?", resolver=lambda cur, ch: None,
                       seq=3, investigation_id="inv-1", document_id="doc-1", events_dir=env["events"])
    assert r.escalated and r.escalated_question_id and r.reserved_child_investigation_id
    # The escalation event carries the reserved (un-launched) child id.
    esc = [r2 for r2 in trajectory("inv-1", events_dir=env["events"])
           if r2["action_type"] == ActionType.QUESTION_ESCALATED_TO_RESEARCH.value]
    assert esc and esc[0]["payload"]["child_investigation_id"] == r.reserved_child_investigation_id
    # No investigation.start_requested — nothing launched here.
    assert all(r2["action_type"] != ActionType.INVESTIGATION_START_REQUESTED.value
               for r2 in trajectory("inv-1", events_dir=env["events"]))


# --------------------------------------------------------------------------
# M5/M7 — scheduler debounce, coalescing, budget backpressure
# --------------------------------------------------------------------------


async def test_scheduler_coalesces_and_processes(env):
    distiller = FakeDistiller(insights=["Sched insight."])
    sched = AsyncNoteScheduler(distiller=distiller, debounce_s=0.0, events_dir=env["events"])
    await sched.submit("doc-1", "v1", investigation_id="inv-1")
    await sched.submit("doc-1", "v2", investigation_id="inv-1")  # coalesces
    await sched.drain()
    assert sched.stats.coalesced == 1
    assert sched.stats.processed == 1
    con = connect_read(env["db"])
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 1
    finally:
        con.close()


async def test_scheduler_budget_backpressure_holds_not_drops(env):
    distiller = FakeDistiller(insights=["x"])
    over_budget = {"ok": False}
    sched = AsyncNoteScheduler(distiller=distiller, debounce_s=0.0,
                               budget_ok=lambda: over_budget["ok"], events_dir=env["events"])
    await sched.submit("doc-1", "t", investigation_id="inv-1")
    await sched.drain()
    assert sched.backlog() == 1          # held, not dropped
    assert sched.stats.processed == 0
    over_budget["ok"] = True             # budget recovers
    await sched.drain()
    assert sched.backlog() == 0 and sched.stats.processed == 1
