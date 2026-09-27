"""W11: a deposited note's groundedness and citation come from source text.

The deposit gate scores a ``note.emerged`` note only against source chunks
(the envelope document's chunks plus the chunks its retrieval evidence
cites), never the pipeline's own decompose agenda or model-written retrieval
answers. The note cites the chunk that supports it, not the document's
longest chunk, and the knowledge unit's groundedness is re-scored against
that cited chunk rather than read back from producer-written metadata.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from processing.embedding import _reset_default_provider
from runtime.db_lock import connect_write
from substrate.context_pack.knowledge_reuse import RetrievedUnit
from substrate.eval.groundedness import score_claim
from substrate.flywheel.reuse_gate import evaluate_unit
from substrate.graph.insight_question import (
    knowledge_unit_of,
    promote_from_note_event,
    promote_insight,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path

SUPPORT = (
    "Venetian banking guilds were shaped by medieval grain tariffs levied on "
    "Adriatic shipping, according to the ledger archive. "
) * 4
FILLER = (
    "The monastery garden grew lavender, rosemary and thyme along the south "
    "wall, and the brothers kept bees for wax. "
) * 30
TARIFF_NOTE = "Medieval grain tariffs shaped Venetian banking guilds."
QUBIT_NOTE = "Photonic qubits reach fault tolerance below the surface code threshold."


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    db = str(tmp_path / "g.duckdb")
    init_database_at_path(db)
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    yield {"db": db, "events": str(events)}
    _reset_default_provider()


def _seed(db: str, *, support: bool) -> None:
    with connect_write(db, purpose="test/seed") as con:
        insert_document(
            con, document_id="doc-1", source_tier=3, document_type="book",
            title="t", raw_text=SUPPORT + FILLER, content_class="public_domain",
        )
        if support:
            insert_chunk(con, document_id="doc-1", chunk_index=0,
                         text=SUPPORT, chunk_id="chunk-support")
        insert_chunk(con, document_id="doc-1", chunk_index=1,
                     text=FILLER, chunk_id="chunk-filler")


def _write(events: str, rows: list[dict]) -> None:
    Path(events, "inv-a.jsonl").write_bytes(
        b"".join(json.dumps(r).encode() + b"\n" for r in rows)
    )


def _note(text: str, *, document_id: str | None = "doc-1",
          source_event_ids: list[str] | None = None) -> dict:
    event = {
        "event_id": "n1", "investigation_id": "inv-a",
        "action_type": "note.emerged",
        "payload": {"note_text": text, "source_event_ids": source_event_ids or []},
        "emitted_at": "2026-01-01T00:00:01Z",
    }
    if document_id:
        event["document_id"] = document_id
    return event


def _meta(db: str, node_id: str) -> dict:
    with connect_write(db, purpose="test/read") as con:
        return json.loads(
            con.execute("SELECT metadata FROM nodes WHERE node_id=?", [node_id]).fetchone()[0]
        )


def test_decompose_agenda_does_not_ground_an_unsupported_note(env) -> None:
    """The investigation's own sub-question restating the note is not
    evidence: the note is refused against the unrelated document."""
    _seed(env["db"], support=False)
    note = _note(QUBIT_NOTE)
    _write(env["events"], [
        {"event_id": "d1", "investigation_id": "inv-a",
         "action_type": "decompose.delivered",
         "payload": {"decomposition": [{
             "sub_question": "Do photonic qubits reach fault tolerance below "
                             "the surface code threshold?",
             "rationale": "threshold"}]},
         "emitted_at": "2026-01-01T00:00:00Z"},
        note,
    ])
    assert promote_from_note_event(
        note, enabled=True, events_dir=env["events"], emit_graph_events=False,
    ) is None


def test_sibling_model_answer_does_not_ground_an_unsupported_note(env) -> None:
    """A retrieval ANSWER is model output; restating the note there is not
    source support."""
    _seed(env["db"], support=False)
    note = _note(QUBIT_NOTE)
    _write(env["events"], [
        {"event_id": "e1", "investigation_id": "inv-a",
         "action_type": "evidence.retrieve.delivered",
         "payload": {"sub_question": "photonic qubits?", "answer": QUBIT_NOTE},
         "emitted_at": "2026-01-01T00:00:00Z"},
        note,
    ])
    assert promote_from_note_event(
        note, enabled=True, events_dir=env["events"], emit_graph_events=False,
    ) is None


def test_note_cites_the_chunk_that_supports_it_not_the_longest(env) -> None:
    _seed(env["db"], support=True)
    note = _note(TARIFF_NOTE)
    _write(env["events"], [note])
    nid = promote_from_note_event(
        note, enabled=True, events_dir=env["events"], emit_graph_events=False,
    )
    assert nid is not None
    meta = _meta(env["db"], nid)
    assert meta["chunk_id"] == "chunk-support"
    own = score_claim(TARIFF_NOTE, [SUPPORT], cited_chunk_ids=["chunk-support"]).score
    assert own >= 0.5
    assert meta["groundedness_score"] == pytest.approx(own)


def test_note_cites_a_chunk_its_retrieval_evidence_cites(env) -> None:
    """A chunk the cited retrieval event rests on is source text; the note
    cites it, with that chunk's own document."""
    _seed(env["db"], support=True)
    note = _note(TARIFF_NOTE, document_id=None, source_event_ids=["e1"])
    _write(env["events"], [
        {"event_id": "e1", "investigation_id": "inv-a",
         "action_type": "evidence.retrieve.delivered",
         "payload": {"sub_question": "tariffs?", "answer": "unrelated prose",
                     "supporting_claims": [{"claim": "c", "chunk_ids": ["chunk-support"]}]},
         "emitted_at": "2026-01-01T00:00:00Z"},
        note,
    ])
    nid = promote_from_note_event(
        note, enabled=True, events_dir=env["events"], emit_graph_events=False,
    )
    assert nid is not None
    meta = _meta(env["db"], nid)
    assert (meta.get("chunk_id"), meta.get("source_document_id")) == ("chunk-support", "doc-1")


def test_reuse_projection_rescores_against_the_cited_chunk(env) -> None:
    """The unit's groundedness is the score against its cited chunk, not a
    number the producer stamped into node metadata."""
    _seed(env["db"], support=False)
    with connect_write(env["db"], purpose="test/deposit") as con:
        nid = promote_insight(
            text=QUBIT_NOTE, investigation_id="inv-a",
            source_document_id="doc-1", chunk_id="chunk-filler",
            metadata={"groundedness_score": 0.99}, con=con,
            emit_graph_events=False,
        )
        unit = knowledge_unit_of(con, nid, score_groundedness=True)
        cited = con.execute(
            "SELECT text FROM chunks WHERE chunk_id='chunk-filler'"
        ).fetchone()[0]
    assert unit.groundedness_score == pytest.approx(
        score_claim(QUBIT_NOTE, [cited], cited_chunk_ids=["chunk-filler"]).score
    )
    decision = evaluate_unit(RetrievedUnit(
        unit=unit, similarity=0.9, content_class="public_domain",
        taken_down=False, same_document=True,
    ))
    assert decision.reusable is False
    assert "below-threshold" in decision.reasons


def test_document_pass_cites_each_insight_to_its_supporting_chunk(env, monkeypatch) -> None:
    import substrate.graph.insight_question as iq
    from roles.note_taker.distill import Distillation
    from roles.note_taker.document_pass import run_document_pass
    from roles.note_taker.parser import ExtractedNote

    monkeypatch.setattr(iq, "graph_db_path", lambda: env["db"])
    c0 = "Chapter one. The lighthouse keeper painted the stairs white every spring."
    c7 = ("Chapter eight. Venetian banking guilds were shaped by medieval grain "
          "tariffs on Adriatic shipping.")
    with connect_write(env["db"], purpose="test/seed") as con:
        insert_document(con, document_id="doc-2", source_tier=3, document_type="book",
                        title="t", raw_text=c0 + "\n\n" + c7, content_class="public_domain")
        insert_chunk(con, document_id="doc-2", chunk_index=0, text=c0, chunk_id="chunk-0")
        insert_chunk(con, document_id="doc-2", chunk_index=7, text=c7, chunk_id="chunk-7")

    class Frozen:
        def distill(self, text, *, source_event_ids=(), context=""):
            return Distillation(insights=[
                ExtractedNote(note_id="n-1", text=TARIFF_NOTE, confidence="high",
                              source_event_ids=("ev-0",)),
                ExtractedNote(note_id="n-2", text=QUBIT_NOTE, confidence="high",
                              source_event_ids=("ev-0",)),
            ])

    res = asyncio.run(run_document_pass(
        "doc-2", c0 + "\n\n" + c7, investigation_id="inv-1", distiller=Frozen(),
        chunk_ids=("chunk-0", "chunk-7"), emit_events=False,
        emit_graph_events=False, events_dir=env["events"],
    ))
    tariff, qubit = res.insight_node_ids
    assert _meta(env["db"], tariff).get("chunk_id") == "chunk-7"
    # No chunk of the document supports the qubit insight: it keeps its
    # document provenance but cites no chunk, so it is not a reusable unit.
    assert _meta(env["db"], qubit).get("chunk_id") is None
    with (
        connect_write(env["db"], purpose="test/read") as con,
        pytest.raises(ValueError, match="no claim"),
    ):
        knowledge_unit_of(con, qubit, score_groundedness=True)
