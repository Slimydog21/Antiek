"""Unlocked note-evidence reads must not nest-flock .delivery.lock (macOS)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import duckdb

from runtime.db_lock import connect_write
from substrate.event_log.events import investigation_event_lock
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import (
    _note_evidence_texts,
    promote_from_note_event,
)
from substrate.graph.ops import insert_chunk, insert_document
from roles.note_taker.replay import _promote_delivered_notes


def _seed(db: str, events: Path, inv: str) -> dict:
    ensure_initialized(db)
    with connect_write(db, purpose="test/seed") as con:
        insert_document(
            con,
            document_id="doc-g",
            title="Gettysburg",
            document_type="book",
            source_tier=1,
            content_class="public_domain",
            raw_text=(
                "Four score and seven years ago our fathers brought forth "
                "on this continent a new nation, conceived in Liberty."
            ),
        )
        insert_chunk(
            con,
            document_id="doc-g",
            chunk_index=0,
            chunk_id="c1",
            text=(
                "Four score and seven years ago our fathers brought forth "
                "on this continent a new nation, conceived in Liberty."
            ),
        )
    note = (
        "Four score and seven years ago the fathers brought forth a new nation "
        "conceived in Liberty on this continent."
    )
    ev_note = {
        "event_id": "evt-note-hi",
        "investigation_id": inv,
        "action_type": "note.emerged",
        "document_id": "doc-g",
        "payload": {
            "note_text": note,
            "note_id": "n-hi",
            "source_event_ids": ["evt-ev"],
            "confidence": "high",
        },
    }
    ev_ev = {
        "event_id": "evt-ev",
        "investigation_id": inv,
        "action_type": "evidence.retrieve.delivered",
        "payload": {
            "sub_question": "What does the passage say?",
            "answer": (
                "Four score and seven years ago our fathers brought forth "
                "a new nation conceived in Liberty."
            ),
        },
    }
    with (events / f"{inv}.jsonl").open("w") as f:
        f.write(json.dumps(ev_ev) + "\n")
        f.write(json.dumps(ev_note) + "\n")
    return ev_note


def test_evidence_load_while_delivery_lock_held(tmp_path: Path, monkeypatch) -> None:
    """Nested flock on macOS blocks; unlocked evidence must still succeed."""
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    inv = "inv-lock"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ev = _seed(db, events, inv)

    # Hold .delivery.lock on another fd (simulates outer iter_physical_events).
    with investigation_event_lock(investigation_id=inv, events_dir=str(events), timeout_s=2.0):
        texts = _note_evidence_texts(ev, events_dir=str(events), con=None)
    assert any("Four score" in t for t in texts)


def test_promote_under_held_delivery_lock(tmp_path: Path, monkeypatch) -> None:
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    inv = "inv-promo-lock"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ev = _seed(db, events, inv)

    with investigation_event_lock(investigation_id=inv, events_dir=str(events), timeout_s=2.0):
        # Must not TimeoutError waiting for the same .delivery.lock.
        nid = promote_from_note_event(
            ev,
            enabled=True,
            emit_graph_events=False,
            events_dir=str(events),
            min_groundedness=0.5,
        )
    assert nid is not None
    con = duckdb.connect(db, read_only=True)
    g = con.execute(
        "SELECT TRY_CAST(json_extract(metadata, '$.groundedness_score') AS DOUBLE) "
        "FROM nodes WHERE node_id=?",
        [nid],
    ).fetchone()[0]
    con.close()
    assert g is not None and g >= 0.5


def test_promote_delivered_notes_under_concurrent_lock_holder(
    tmp_path: Path, monkeypatch
) -> None:
    """Simulates catch_up holding delivery.lock while promote batch runs."""
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    inv = "inv-batch"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _seed(db, events, inv)

    errors: list[BaseException] = []
    hold = threading.Event()
    started = threading.Event()

    def holder() -> None:
        with investigation_event_lock(
            investigation_id=inv, events_dir=str(events), timeout_s=5.0
        ):
            started.set()
            hold.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    assert started.wait(2)
    try:
        _promote_delivered_notes(
            inv,
            ["evt-note-hi"],
            events_dir=str(events),
            db_path=db,
        )
    except BaseException as exc:  # noqa: BLE001
        errors.append(exc)
    finally:
        hold.set()
        t.join(timeout=5)

    assert errors == []
    con = duckdb.connect(db, read_only=True)
    n = con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
    con.close()
    assert n == 1
