"""Loop One events qualify for note-taker; notes promote into distill."""

from __future__ import annotations

import json

from roles.note_taker.distill_query import distillation_for
from roles.note_taker.replay import QUALIFYING_ACTION_TYPES, DurableNoteTakerReplay
from substrate.event_log import emit_typed
from substrate.graph import ensure_initialized
from substrate.schemas.events import (
    ActionType,
    EvidenceRetrieveDeliveredPayload,
)


def test_loop_one_action_types_qualify():
    assert ActionType.EVIDENCE_RETRIEVE_DELIVERED.value in QUALIFYING_ACTION_TYPES
    assert ActionType.SYNTHESIZE_DELIVERED.value in QUALIFYING_ACTION_TYPES
    assert ActionType.DECOMPOSE_QUESTION_DELIVERED.value in QUALIFYING_ACTION_TYPES


def _evidence(events_dir: str, count: int, inv: str = "inv-loop1") -> None:
    for i in range(count):
        emit_typed(
            inv,
            EvidenceRetrieveDeliveredPayload(
                sub_question=f"Aspect {i} of the thesis?",
                answer=f"Evidence answer {i} grounded in the corpus.",
                supporting_claims=[],
                evidentiary_gaps=[],
                insufficient_evidence=True,
            ),
            events_dir=events_dir,
            role="evidence_retriever",
            document_id="doc-loop1",
        )


def _note_response(request, idempotency_key=None):
    # The deposit-time groundedness bar (b7dc0ec77, min_groundedness=0.5)
    # honestly refuses notes with no lexical entailment in the cited
    # evidence. This note summarizes the evidence the window emitted
    # ("Evidence answer i grounded in the corpus."), so it clears the bar
    # on its own merit — the promote path being exercised end-to-end.
    return json.dumps(
        {
            "notes": [
                {
                    "text": "Gettysburg evidence answer grounded in the corpus.",
                    "confidence": "high",
                    "source_event_ids": request["source_event_ids"],
                }
            ]
        }
    )


def test_evidence_retrieve_windows_promote_into_distill(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    ensure_initialized(db)

    inv = "inv-loop1"
    _evidence(str(events), 5, inv=inv)

    delivered = DurableNoteTakerReplay(
        _note_response,
        db_path=db,
        events_dir=str(events),
        threshold=5,
    ).catch_up(inv)
    assert delivered  # note.emerged event ids

    view = distillation_for(inv, db_path=db, events_dir=str(events))
    assert not view.empty
    assert any("Gettysburg" in n.text for n in view.insights)
