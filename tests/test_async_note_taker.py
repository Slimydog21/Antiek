"""DRW SPR-03 — always-on note-taking + living notes.

Mechanical gates: document pass promotes provenance-carrying nodes; step
pass dedupes within a run; living-note updates are deterministic by event
seq under concurrent challenge + background edit; unresolvable challenge
escalates (without launching); idempotent re-runs promote zero; scheduler
debounces + applies budget backpressure.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager

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
    living_note_history,
    notes_for_step,
    run_document_pass,
)
from roles.note_taker.living_note import (
    ChallengeRequestConflict,
    ChallengeRequestInProgress,
    LivingNoteScopeConflict,
)
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read, connect_write
from substrate.context_pack import build_working_memory_layer
from substrate.event_log import emit_typed, iter_physical_events, trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.schema import init_database, init_database_at_path
from substrate.schemas.events import ActionType, DistillationRequestedPayload


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


async def test_supplied_connection_requires_explicit_commit_mode_before_distillation(env):
    called = False

    class RecordingDistiller(FakeDistiller):
        def distill(self, text, *, source_event_ids=(), context=""):
            nonlocal called
            called = True
            return super().distill(text, source_event_ids=source_event_ids, context=context)

    con = connect_write(env["db"], purpose="test_missing_commit_mode")
    try:
        with pytest.raises(ValueError, match="explicit commit mode"):
            await run_document_pass(
                "doc-1", "source", investigation_id="inv-1",
                distiller=RecordingDistiller(insights=["Must not run."]),
                con=con, events_dir=env["events"],
            )
    finally:
        con.close()
    assert not called
    assert trajectory("inv-1", events_dir=env["events"]) == []


async def test_caller_owned_transaction_rejects_external_publication_before_distillation(env):
    called = False

    class RecordingDistiller(FakeDistiller):
        def distill(self, text, *, source_event_ids=(), context=""):
            nonlocal called
            called = True
            return super().distill(text, source_event_ids=source_event_ids, context=context)

    con = connect_write(env["db"], purpose="test_caller_owned_publication")
    try:
        with pytest.raises(ValueError, match="cannot publish before commit"):
            await run_document_pass(
                "doc-1", "source", investigation_id="inv-1",
                distiller=RecordingDistiller(insights=["Must not run."]),
                con=con, connection_commit_mode="caller_owned",
                events_dir=env["events"],
            )
    finally:
        con.close()
    assert not called
    assert trajectory("inv-1", events_dir=env["events"]) == []
    with connect_read(env["db"]) as read:
        assert read.execute("SELECT count(*) FROM nodes").fetchone()[0] == 0


async def test_caller_owned_silent_promotion_can_be_rolled_back_without_external_identity(env):
    con = connect_write(env["db"], purpose="test_caller_owned_rollback")
    try:
        con.execute("BEGIN")
        result = await run_document_pass(
            "doc-1", "source", investigation_id="inv-1",
            distiller=FakeDistiller(insights=["Rollback hypothesis."]),
            con=con, connection_commit_mode="caller_owned",
            emit_events=False, emit_graph_events=False, events_dir=env["events"],
        )
        assert len(result.insight_node_ids) == 1
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == 1
        con.execute("ROLLBACK")
    finally:
        con.close()
    assert trajectory("inv-1", events_dir=env["events"]) == []
    with connect_read(env["db"]) as read:
        assert read.execute("SELECT count(*) FROM nodes").fetchone()[0] == 0


async def test_question_event_is_not_published_when_promotion_fails(env, monkeypatch):
    import roles.note_taker.document_pass as document_pass

    def fail_promotion(**_kwargs):
        raise RuntimeError("injected question promotion failure")

    monkeypatch.setattr(document_pass, "promote_question", fail_promotion)
    with pytest.raises(RuntimeError, match="injected question promotion failure"):
        await run_document_pass(
            "doc-1", "source", investigation_id="inv-1",
            distiller=FakeDistiller(questions=["Uncommitted question?"]),
            events_dir=env["events"],
        )
    assert [
        event for event in trajectory("inv-1", events_dir=env["events"])
        if event["action_type"] == ActionType.QUESTION_IDENTIFIED.value
    ] == []


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


def _promoted_emerged_note(env, *, text="Base.", note_id="note-origin"):
    return promote_insight(
        text=text,
        investigation_id="inv-1",
        source_document_id="doc-1",
        metadata={"origin_note_id": note_id},
    )


async def test_refinement_rolls_back_graph_and_outbox_before_commit(env):
    nid = _promoted_emerged_note(env)

    def fail(stage):
        if stage == "after_enqueue_before_commit":
            raise RuntimeError("pre-commit failure")

    with pytest.raises(RuntimeError, match="pre-commit failure"):
        apply_refinement(
            nid, "Changed.", seq=1, investigation_id="inv-1",
            events_dir=env["events"], _checkpoint=fail,
        )
    con = connect_read(env["db"])
    try:
        text, metadata = con.execute(
            "SELECT canonical_label, metadata FROM nodes WHERE node_id=?", [nid]
        ).fetchone()
        assert text == "Base."
        assert json.loads(metadata).get("refinement_count", 0) == 0
        assert con.execute("SELECT COUNT(*) FROM write_event_outbox").fetchone()[0] == 0
    finally:
        con.close()
    assert not [
        row for row in trajectory("inv-1", events_dir=env["events"])
        if row["action_type"] == ActionType.NOTE_REFINED.value
    ]


async def test_refinement_transaction_locks_custom_event_stream(env, monkeypatch):
    import roles.note_taker.living_note as living_note

    nid = _promoted_emerged_note(env)
    observed = []
    original = living_note.eventful_transaction

    @contextmanager
    def recording_transaction(con, investigation_id, *, events_dir=None):
        observed.append((investigation_id, events_dir))
        with original(con, investigation_id, events_dir=events_dir):
            yield

    monkeypatch.setattr(living_note, "eventful_transaction", recording_transaction)
    apply_refinement(
        nid, "Changed.", seq=1, investigation_id="inv-1",
        events_dir=env["events"],
    )
    assert observed == [("inv-1", env["events"])]


async def test_refinement_exact_retry_recovers_pending_delivery_once(env):
    nid = _promoted_emerged_note(env)

    def fail(stage):
        if stage == "after_commit_before_delivery":
            raise RuntimeError("post-commit failure")

    with pytest.raises(RuntimeError, match="post-commit failure"):
        apply_refinement(
            nid, "Changed.", seq=1, investigation_id="inv-1",
            events_dir=env["events"], _checkpoint=fail,
        )
    con = connect_read(env["db"])
    try:
        text, metadata = con.execute(
            "SELECT canonical_label, metadata FROM nodes WHERE node_id=?", [nid]
        ).fetchone()
        assert text == "Changed."
        assert json.loads(metadata)["refinement_count"] == 1
        assert con.execute(
            "SELECT state FROM write_event_outbox"
        ).fetchone()[0] == "pending"
    finally:
        con.close()

    replay = apply_refinement(
        nid, "Changed.", seq=1, investigation_id="inv-1",
        events_dir=env["events"],
    )
    assert replay.applied and not replay.superseded
    rows = [
        row for row in trajectory("inv-1", events_dir=env["events"])
        if row["action_type"] == ActionType.NOTE_REFINED.value
    ]
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["origin_note_id"] == "note-origin"
    assert payload["sequence"] == 1
    assert payload["previous_sequence"] == -1
    assert payload["outcome"] == "applied"
    con = connect_read(env["db"])
    try:
        assert json.loads(con.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [nid]
        ).fetchone()[0])["refinement_count"] == 1
        assert con.execute(
            "SELECT state, attempt_count FROM write_event_outbox"
        ).fetchone() == ("delivered", 1)
    finally:
        con.close()


async def test_distinct_same_sequence_attempt_is_durably_superseded(env):
    nid = _promoted_emerged_note(env)
    winner = apply_refinement(
        nid, "Winner.", seq=4, investigation_id="inv-1", events_dir=env["events"]
    )
    loser = apply_refinement(
        nid, "Losing attempt.", seq=4, investigation_id="inv-1",
        events_dir=env["events"],
    )
    assert winner.applied
    assert loser.superseded and not loser.applied
    rows = [
        row for row in trajectory("inv-1", events_dir=env["events"])
        if row["action_type"] == ActionType.NOTE_REFINED.value
    ]
    assert [row["payload"]["outcome"] for row in rows] == [
        "applied", "superseded"
    ]
    assert rows[1]["payload"]["previous_text"] == "Winner."
    assert rows[1]["payload"]["new_text"] == "Losing attempt."
    assert rows[1]["payload"]["previous_sequence"] == 4


async def test_document_note_refinement_becomes_causal_working_memory(env):
    result = await run_document_pass(
        "doc-1",
        "source text",
        investigation_id="inv-1",
        distiller=FakeDistiller(insights=["Emerged hypothesis."]),
        chunk_ids=["chunk-1"],
        source_event_ids=["source-1"],
        events_dir=env["events"],
    )
    assert len(result.insight_node_ids) == 1
    refinement = apply_refinement(
        result.insight_node_ids[0],
        "Authoritative hypothesis.",
        seq=1,
        investigation_id="inv-1",
        events_dir=env["events"],
    )
    assert refinement.applied
    cutoff_id = emit_typed(
        "inv-1",
        DistillationRequestedPayload(
            region_id="region-1",
            user_prompt="What follows?",
            target_token_count=100,
        ),
        document_id="doc-1",
        events_dir=env["events"],
    )
    assert cutoff_id is not None

    layer = build_working_memory_layer(
        list(iter_physical_events("inv-1", events_dir=env["events"])),
        investigation_id="inv-1",
        cutoff_event_id=cutoff_id,
    )
    assert layer is not None
    assert "Authoritative hypothesis." in layer.content
    assert "Emerged hypothesis." not in layer.content


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
    nid = promote_insight(
        text="Margins are healthy.", investigation_id="inv-1",
        source_document_id="doc-1",
    )
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


async def test_challenge_retry_after_decision_skips_resolver(env):
    nid = promote_insight(
        text="Acme is small.", investigation_id="inv-1",
        source_document_id="doc-1",
    )
    calls = 0

    def resolver(current, challenge):
        nonlocal calls
        calls += 1
        return "Acme is mid-sized."

    def fail(stage):
        if stage == "after_challenge_decision_before_apply":
            raise RuntimeError("injected after decision")

    with pytest.raises(RuntimeError, match="after decision"):
        challenge_note(
            nid, "it grew", resolver=resolver, seq=1,
            investigation_id="inv-1", events_dir=env["events"],
            idempotency_key="challenge-decision-0001", _checkpoint=fail,
        )
    result = challenge_note(
        nid, "it grew", resolver=resolver, seq=99,
        investigation_id="inv-1", events_dir=env["events"],
        idempotency_key="challenge-decision-0001",
    )
    assert result.applied
    assert calls == 1


async def test_challenge_retry_after_graph_commit_skips_resolver(env):
    nid = promote_insight(
        text="Acme is small.", investigation_id="inv-1",
        source_document_id="doc-1",
    )
    calls = 0

    def resolver(current, challenge):
        nonlocal calls
        calls += 1
        return "Acme is mid-sized."

    def fail(stage):
        if stage == "after_challenge_apply_before_complete":
            raise RuntimeError("injected after graph apply")

    with pytest.raises(RuntimeError, match="after graph apply"):
        challenge_note(
            nid, "it grew", resolver=resolver, seq=1,
            investigation_id="inv-1", events_dir=env["events"],
            idempotency_key="challenge-graph-commit-1", _checkpoint=fail,
        )
    result = challenge_note(
        nid, "it grew", resolver=resolver, seq=99,
        investigation_id="inv-1", events_dir=env["events"],
        idempotency_key="challenge-graph-commit-1",
    )
    assert result.applied
    assert calls == 1


async def test_ambiguous_resolver_completion_is_not_dispatched_again(env):
    nid = promote_insight(
        text="Acme is small.", investigation_id="inv-1",
        source_document_id="doc-1",
    )
    calls = 0

    def resolver(current, challenge):
        nonlocal calls
        calls += 1
        return "Acme is mid-sized."

    def fail(stage):
        if stage == "after_challenge_resolver_before_decision":
            raise RuntimeError("injected ambiguous completion")

    with pytest.raises(RuntimeError, match="ambiguous completion"):
        challenge_note(
            nid, "it grew", resolver=resolver, seq=1,
            investigation_id="inv-1", events_dir=env["events"],
            idempotency_key="challenge-ambiguous-01", _checkpoint=fail,
        )
    with pytest.raises(ChallengeRequestInProgress):
        challenge_note(
            nid, "it grew", resolver=resolver, seq=99,
            investigation_id="inv-1", events_dir=env["events"],
            idempotency_key="challenge-ambiguous-01",
        )
    assert calls == 1


async def test_escalation_rolls_back_graph_and_outbox_before_commit(env):
    nid = promote_insight(
        text="Margins are healthy.", investigation_id="inv-1",
        source_document_id="doc-1",
    )

    def fail(stage):
        if stage == "after_escalation_enqueue_before_commit":
            raise RuntimeError("injected pre-commit failure")

    with pytest.raises(RuntimeError, match="pre-commit"):
        challenge_note(
            nid, "Source for margins?", resolver=lambda cur, ch: None,
            seq=3, investigation_id="inv-1", events_dir=env["events"],
            _checkpoint=fail,
        )
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM nodes WHERE node_type='question'"
        ).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM write_event_outbox").fetchone()[0] == 0
    finally:
        con.close()


async def test_escalation_retry_recovers_one_ordered_bundle(env):
    nid = promote_insight(
        text="Margins are healthy.", investigation_id="inv-1",
        source_document_id="doc-1",
    )

    def fail(stage):
        if stage == "after_escalation_commit_before_delivery":
            raise RuntimeError("injected post-commit failure")

    with pytest.raises(RuntimeError, match="post-commit"):
        challenge_note(
            nid, "Source for margins?", resolver=lambda cur, ch: None,
            seq=3, investigation_id="inv-1", events_dir=env["events"],
            _checkpoint=fail,
        )
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT state, COUNT(*) FROM write_event_outbox GROUP BY state"
        ).fetchall() == [("pending", 3)]
    finally:
        con.close()

    recovered = challenge_note(
        nid, "Source for margins?", resolver=lambda cur, ch: None,
        seq=3, investigation_id="inv-1", events_dir=env["events"],
    )
    repeated = challenge_note(
        nid, "Source for margins?", resolver=lambda cur, ch: None,
        seq=3, investigation_id="inv-1", events_dir=env["events"],
    )
    assert recovered == repeated
    relevant = [
        row["action_type"] for row in trajectory("inv-1", events_dir=env["events"])
        if row["action_type"] in {
            ActionType.GRAPH_NODE_INSERTED.value,
            ActionType.GRAPH_EDGE_INSERTED.value,
            ActionType.QUESTION_ESCALATED_TO_RESEARCH.value,
        }
    ]
    assert relevant[-3:] == [
        ActionType.GRAPH_NODE_INSERTED.value,
        ActionType.GRAPH_EDGE_INSERTED.value,
        ActionType.QUESTION_ESCALATED_TO_RESEARCH.value,
    ]
    assert relevant.count(ActionType.QUESTION_ESCALATED_TO_RESEARCH.value) == 1


async def test_same_challenge_text_is_scoped_to_the_challenged_note(env):
    first = promote_insight(
        text="Margins are healthy.", investigation_id="inv-1",
        source_document_id="doc-1",
    )
    second = promote_insight(
        text="Demand is durable.", investigation_id="inv-1",
        source_document_id="doc-2",
    )
    a = challenge_note(
        first, "What is the source?", resolver=lambda cur, ch: None,
        seq=1, investigation_id="inv-1", events_dir=env["events"],
    )
    b = challenge_note(
        second, "What is the source?", resolver=lambda cur, ch: None,
        seq=1, investigation_id="inv-1", events_dir=env["events"],
    )
    assert a.escalated_question_id != b.escalated_question_id
    assert a.reserved_child_investigation_id != b.reserved_child_investigation_id
    con = connect_read(env["db"])
    try:
        rows = con.execute(
            "SELECT source_node_id, target_node_id FROM edges "
            "WHERE relation='asks_about' ORDER BY target_node_id"
        ).fetchall()
        assert set(rows) == {
            (a.escalated_question_id, first),
            (b.escalated_question_id, second),
        }
    finally:
        con.close()


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


async def test_shared_node_is_visible_and_challengeable_from_each_member(env):
    first = await run_document_pass(
        "doc-a", "src", investigation_id="inv-a",
        distiller=FakeDistiller(insights=["A shared fact."]), events_dir=env["events"],
    )
    second = await run_document_pass(
        "doc-b", "src", investigation_id="inv-b",
        distiller=FakeDistiller(insights=["A shared fact."]), events_dir=env["events"],
    )
    assert first.insight_node_ids == second.insight_node_ids
    nid = first.insight_node_ids[0]
    assert [n.node_id for n in distillation_for(
        "inv-a", db_path=env["db"], events_dir=env["events"]
    ).insights] == [nid]
    assert [n.node_id for n in distillation_for(
        "inv-b", db_path=env["db"], events_dir=env["events"]
    ).insights] == [nid]

    result = challenge_note(
        nid, "sharpen", resolver=lambda _cur, _challenge: "A refined shared fact.",
        seq=1, investigation_id="inv-b", events_dir=env["events"],
    )
    assert result.applied
    refined = [
        row for row in trajectory("inv-b", events_dir=env["events"])
        if row["action_type"] == "note.refined"
    ]
    assert refined[-1]["payload"]["origin_note_id"] == "n-0"

    history_a = living_note_history("inv-a", nid, db_path=env["db"])
    history_b = living_note_history("inv-b", nid, db_path=env["db"])
    assert history_a.entries == history_b.entries
    assert history_a.entries[0].source_investigation_id == "inv-b"

    resolver_called = False

    def foreign_resolver(_current, _challenge):
        nonlocal resolver_called
        resolver_called = True
        return "must not run"

    with pytest.raises(LivingNoteScopeConflict, match="does not belong"):
        challenge_note(
            nid, "foreign", resolver=foreign_resolver, seq=2,
            investigation_id="inv-c", events_dir=env["events"],
        )
    assert not resolver_called


async def test_repeated_node_observations_target_exact_live_note(env):
    nid = promote_insight(
        text="Repeated fact.", investigation_id="inv-1",
        source_document_id="doc-a", metadata={"origin_note_id": "note-a"},
    )
    assert promote_insight(
        text="Repeated fact.", investigation_id="inv-1",
        source_document_id="doc-b", metadata={"origin_note_id": "note-b"},
    ) == nid
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT origin_note_id, source_document_id "
            "FROM node_investigation_observations WHERE node_id=? "
            "ORDER BY origin_note_id",
            [nid],
        ).fetchall() == [("note-a", "doc-a"), ("note-b", "doc-b")]
    finally:
        con.close()

    result = challenge_note(
        nid, "sharpen", resolver=lambda _cur, _challenge: "Refined repeated fact.",
        seq=1, investigation_id="inv-1", origin_note_id="note-b",
        events_dir=env["events"], idempotency_key="observation-command-0001",
    )
    assert result.applied
    refined = [
        row for row in trajectory("inv-1", events_dir=env["events"])
        if row["action_type"] == "note.refined"
    ][-1]
    assert refined["document_id"] == "doc-b"
    assert refined["payload"]["origin_note_id"] == "note-b"

    promote_insight(
        text="Repeated fact.", investigation_id="inv-2",
        source_document_id="doc-c", metadata={"origin_note_id": "note-c"},
    )
    called = False

    def substituted_resolver(_current, _challenge):
        nonlocal called
        called = True
        return "must not run"

    with pytest.raises(LivingNoteScopeConflict, match="observation"):
        challenge_note(
            nid, "foreign observation", resolver=substituted_resolver,
            seq=2, investigation_id="inv-1", origin_note_id="note-c",
            events_dir=env["events"], idempotency_key="observation-command-0002",
        )
    assert not called


async def test_owned_repeated_observations_do_not_redefine_private_node(env):
    nid = promote_insight(
        text="Private repeated fact.", investigation_id="inv-1",
        source_document_id="doc-a", metadata={"origin_note_id": "note-a"},
        owner_user_id="owner-1", identity_scope="owner-1",
    )
    assert promote_insight(
        text="Private repeated fact.", investigation_id="inv-1",
        source_document_id="doc-b", metadata={"origin_note_id": "note-b"},
        owner_user_id="owner-1", identity_scope="owner-1",
    ) == nid
    con = connect_read(env["db"])
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM node_investigation_observations WHERE node_id=?",
            [nid],
        ).fetchone()[0] == 2
    finally:
        con.close()


def test_observation_migration_backfills_legacy_membership_idempotently(env):
    nid = promote_insight(
        text="Legacy observation.", investigation_id="inv-1",
        source_document_id="doc-legacy", metadata={"origin_note_id": "note-legacy"},
    )
    con = connect_write(env["db"], purpose="test_observation_backfill")
    try:
        con.execute("DELETE FROM node_investigation_observations WHERE node_id=?", [nid])
        init_database(con)
        init_database(con)
        assert con.execute(
            "SELECT origin_note_id, source_document_id "
            "FROM node_investigation_observations WHERE node_id=?",
            [nid],
        ).fetchall() == [("note-legacy", "doc-legacy")]
    finally:
        con.close()


async def test_challenge_idempotency_key_binds_observation(env):
    nid = promote_insight(
        text="One node.", investigation_id="inv-1", source_document_id="doc-a",
        metadata={"origin_note_id": "note-a"},
    )
    promote_insight(
        text="One node.", investigation_id="inv-1", source_document_id="doc-b",
        metadata={"origin_note_id": "note-b"},
    )
    key = "observation-command-bind-0001"
    challenge_note(
        nid, "same command", resolver=lambda _cur, _challenge: "Changed.",
        seq=1, investigation_id="inv-1", origin_note_id="note-a",
        events_dir=env["events"], idempotency_key=key,
    )
    with pytest.raises(ChallengeRequestConflict, match="another challenge"):
        challenge_note(
            nid, "same command", resolver=lambda _cur, _challenge: "Wrong.",
            seq=2, investigation_id="inv-1", origin_note_id="note-b",
            events_dir=env["events"], idempotency_key=key,
        )


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
