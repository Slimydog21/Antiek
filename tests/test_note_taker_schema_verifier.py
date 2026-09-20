from __future__ import annotations

import json

import pytest

from roles.note_taker.replay import DurableNoteTakerReplay
from runtime.db_lock import connect_write
from substrate.event_log import emit_typed
from substrate.schemas.events import ClaimGroundingCheckPassedPayload
from tools.verify_note_taker_schema import verify


def _events(root) -> None:
    for index in range(5):
        emit_typed(
            "inv-1",
            ClaimGroundingCheckPassedPayload(
                claim_id=f"c-{index}",
                claim_text=f"claim {index}",
                located_region_id=f"r-{index}",
                confidence=0.9,
            ),
            document_id="doc-1",
            events_dir=str(root),
            role="grounder",
        )


def _response(request, idempotency_key=None):
    return json.dumps(
        {
            "notes": [
                {
                    "text": "durable",
                    "confidence": "high",
                    "source_event_ids": request["source_event_ids"],
                }
            ]
        }
    )


def test_verifier_accepts_coherent_completed_window(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _events(events)
    DurableNoteTakerReplay(
        _response, db_path=db, events_dir=str(events)
    ).catch_up("inv-1")
    verify(db)


def test_verifier_accepts_completed_window_with_valid_zero_notes(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _events(events)
    DurableNoteTakerReplay(
        lambda request, idempotency_key=None: '{"notes":[]}',
        db_path=db,
        events_dir=str(events),
    ).catch_up("inv-1")
    verify(db)
    with connect_write(db, purpose="test/read-zero-note-window") as con:
        assert con.execute(
            "SELECT state FROM note_taker_windows"
        ).fetchone() == ("completed",)
        assert con.execute(
            "SELECT COUNT(*) FROM write_event_outbox WHERE "
            "aggregate_kind='note_taker_window'"
        ).fetchone() == (0,)


def test_verifier_rejects_configuration_digest_corruption(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _events(events)
    DurableNoteTakerReplay(
        _response, db_path=db, events_dir=str(events)
    ).catch_up("inv-1")
    with connect_write(db, purpose="test/corrupt-note-config") as con:
        con.execute(
            "UPDATE note_taker_configurations SET configuration_sha256=?",
            ["0" * 64],
        )
    with pytest.raises(RuntimeError, match="configuration digest"):
        verify(db)


def test_verifier_rejects_completed_window_with_pending_event(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    _events(events)
    DurableNoteTakerReplay(
        _response, db_path=db, events_dir=str(events)
    ).catch_up("inv-1")
    with connect_write(db, purpose="test/corrupt-note-outbox") as con:
        con.execute(
            "UPDATE write_event_outbox SET state='pending', delivered_at=NULL "
            "WHERE aggregate_kind='note_taker_window'"
        )
    with pytest.raises(RuntimeError, match="pending completed"):
        verify(db)
