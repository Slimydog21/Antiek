"""DRW SPR-03 — always-on note-taking + living notes.

Mechanical gates: document pass promotes provenance-carrying nodes; step
pass dedupes within a run; living-note updates are deterministic by event
seq under concurrent challenge + background edit; unresolvable challenge
escalates (without launching); idempotent re-runs promote zero; scheduler
debounces + applies budget backpressure.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.challenger import ChallengeUnavailable, make_dispatch_resolver, parse_resolution
from roles.note_taker import (
    AsyncNoteScheduler,
    Distillation,
    DistilledQuestion,
    RunNoteDeduper,
    apply_refinement,
    challenge_note,
    distillation_for,
    notes_for_step,
    run_document_pass,
)
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read
from substrate.event_log import trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ActionType


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


async def test_document_pass_threads_canonical_source_event_ids(env):
    observed = {}

    class RecordingDistiller(FakeDistiller):
        def distill(self, text, *, source_event_ids=(), context=""):
            observed["source_event_ids"] = tuple(source_event_ids)
            return super().distill(
                text, source_event_ids=source_event_ids, context=context
            )

    await run_document_pass(
        "doc-1",
        "source",
        investigation_id="inv-1",
        distiller=RecordingDistiller(insights=["Grounded insight."]),
        chunk_ids=["c1"],
        source_event_ids=("event-source-1",),
        events_dir=env["events"],
    )
    assert observed == {"source_event_ids": ("event-source-1",)}


async def test_document_pass_drops_notes_that_discard_or_forge_required_sources(env):
    class UnattributedDistiller(FakeDistiller):
        def distill(self, text, *, source_event_ids=(), context=""):
            return Distillation(
                insights=[
                    ExtractedNote(
                        note_id="missing",
                        text="Missing source.",
                        confidence="high",
                        source_event_ids=(),
                    ),
                    ExtractedNote(
                        note_id="forged",
                        text="Forged source.",
                        confidence="high",
                        source_event_ids=("event-forged",),
                    ),
                    ExtractedNote(
                        note_id="partial",
                        text="Partial source set.",
                        confidence="high",
                        source_event_ids=("event-source-1",),
                    ),
                ]
            )

    result = await run_document_pass(
        "doc-1",
        "source",
        investigation_id="inv-1",
        distiller=UnattributedDistiller(),
        source_event_ids=("event-source-1", "event-source-2"),
        events_dir=env["events"],
    )
    assert result.insight_node_ids == []
    assert result.dropped_provenance_free == 3


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


# --------------------------------------------------------------------------
# SPR-03 surface — M2 read seam (distillation_for)
# --------------------------------------------------------------------------


async def test_distillation_for_reads_insights_questions_with_grounding(env):
    await run_document_pass(
        "doc-1", "src", investigation_id="inv-1",
        distiller=FakeDistiller(insights=["GPUs gate scale."], questions=["What is the moat?"]),
        chunk_ids=["c1"], events_dir=env["events"],
    )
    view = distillation_for("inv-1", db_path=env["db"], events_dir=env["events"])
    assert [n.text for n in view.insights] == ["GPUs gate scale."]
    assert [n.text for n in view.questions] == ["What is the moat?"]
    # Grounding (the document) rides on the node, not re-derived in the surface.
    assert view.insights[0].source_document_id == "doc-1"
    assert view.insights[0].confidence == "moderate"
    assert not view.empty


async def test_distillation_for_empty_when_no_notes(env):
    # No provider / no pass run → honest empty result, never canned content.
    view = distillation_for("inv-empty", db_path=env["db"], events_dir=env["events"])
    assert view.empty and view.insights == [] and view.questions == []


async def test_distillation_for_reflects_living_note_in_place(env):
    # A challenge mutates the note; the surface reads the *current* text from
    # the node row, not the original note.emerged payload.
    nid = promote_insight(text="Acme is small.", investigation_id="inv-1",
                          source_document_id="doc-1")
    challenge_note(nid, "it grew", resolver=lambda cur, ch: "Acme is mid-sized.",
                   seq=1, investigation_id="inv-1", events_dir=env["events"])
    view = distillation_for("inv-1", db_path=env["db"], events_dir=env["events"])
    # The promote emits a GRAPH_NODE_INSERTED the read seam picks up; the text
    # is the refined one, the count reflects the single refinement.
    assert [n.text for n in view.insights] == ["Acme is mid-sized."]
    assert view.insights[0].refinement_count == 1


async def test_distillation_for_surfaces_escalated_question(env):
    nid = promote_insight(text="Margins are healthy.", investigation_id="inv-1",
                          source_document_id="doc-1")
    r = challenge_note(nid, "source for margins?", resolver=lambda cur, ch: None,
                       seq=1, investigation_id="inv-1", events_dir=env["events"])
    view = distillation_for("inv-1", db_path=env["db"], events_dir=env["events"])
    escalated = [q for q in view.questions if q.escalated]
    assert escalated, "the escalated challenge surfaces as an open question"
    assert escalated[0].reserved_child_investigation_id == r.reserved_child_investigation_id


# --------------------------------------------------------------------------
# SPR-03 — M3 no-duplicate-via-challenge + determinism through the resolver
# --------------------------------------------------------------------------


async def test_challenge_resolves_no_duplicate_node(env):
    nid = promote_insight(text="Claim v1.", investigation_id="inv-1",
                          source_document_id="doc-1")
    before = _insight_count(env["db"])
    challenge_note(nid, "sharpen it", resolver=lambda cur, ch: "Claim v2.",
                   seq=1, investigation_id="inv-1", events_dir=env["events"])
    after = _insight_count(env["db"])
    assert before == after == 1          # mutated in place, no new node
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT canonical_label FROM nodes WHERE node_id=?", [nid]
        ).fetchone()[0] == "Claim v2."
    finally:
        con.close()


async def test_living_note_determinism_independent_of_resolver(env):
    # The seq rule is owned by apply_refinement; a user challenge at the
    # higher seq wins over a stale background refinement regardless of who the
    # resolver is. (Drives the shipped rule; resolver supplies content only.)
    nid = promote_insight(text="Base.", investigation_id="inv-1",
                          source_document_id="doc-1")
    # Background refinement lands first at seq=11.
    apply_refinement(nid, "background-seq-11", seq=11, investigation_id="inv-1",
                     document_id="doc-1", events_dir=env["events"])
    # The user challenge arrives at seq=12 via the resolver path.
    r = challenge_note(nid, "user challenge", resolver=lambda cur, ch: "user-seq-12",
                       seq=12, investigation_id="inv-1", document_id="doc-1",
                       events_dir=env["events"])
    assert r.applied
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT canonical_label FROM nodes WHERE node_id=?", [nid]
        ).fetchone()[0] == "user-seq-12"
    finally:
        con.close()


def _insight_count(db: str) -> int:
    con = connect_read(db)
    try:
        return con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
    finally:
        con.close()


# --------------------------------------------------------------------------
# SPR-03 — M4 challenger resolver: refine-or-decline parsing + honest no-key
# --------------------------------------------------------------------------


def test_resolver_parse_refine_returns_text():
    out = parse_resolution(
        '{"resolution": "refine", "refined_text": "A sharper claim."}',
        current_text="A claim.",
    )
    assert out == "A sharper claim."


def test_resolver_parse_needs_research_declines():
    out = parse_resolution(
        '{"resolution": "needs_research", "refined_text": ""}',
        current_text="A claim.",
    )
    assert out is None                   # declines → escalation, not a fake edit


def test_resolver_parse_noop_refinement_declines():
    # A "refinement" identical to the note is a no-op dressed as a change.
    out = parse_resolution(
        '{"resolution": "refine", "refined_text": "A  CLAIM."}',
        current_text="A claim.",
    )
    assert out is None


def test_resolver_parse_malformed_declines():
    assert parse_resolution("not json at all", current_text="x") is None


def test_dispatch_resolver_no_provider_raises_unavailable(monkeypatch):
    # With no model registered, dispatch raises; the resolver must surface
    # ChallengeUnavailable (honest no-key) — never silently fabricate text
    # and never escalate as if the graph couldn't resolve it.
    import substrate.dispatch as dispatch_pkg

    def _boom(*a, **k):
        # No provider registered → get_provider raises KeyError; the role
        # missing from config also raises KeyError. Either is the no-key path.
        raise KeyError("Provider 'anthropic' is not registered")

    monkeypatch.setattr(dispatch_pkg, "dispatch", _boom)
    resolver = make_dispatch_resolver("inv-1")
    with pytest.raises(ChallengeUnavailable):
        resolver("the note", "the challenge")
