"""Refuse promote_from_note_event when groundedness < reuse bar."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_from_note_event
from substrate.graph.ops import insert_chunk, insert_document


def _init_doc(db: str, doc: str = "doc-g") -> None:
    ensure_initialized(db)
    with connect_write(db, purpose="test/seed") as con:
        insert_document(
            con,
            document_id=doc,
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
            document_id=doc,
            chunk_index=0,
            chunk_id="c1",
            text=(
                "Four score and seven years ago our fathers brought forth "
                "on this continent a new nation, conceived in Liberty."
            ),
        )


def test_refuse_promote_when_below_groundedness(tmp_path: Path, monkeypatch) -> None:
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _init_doc(db)
    inv = "inv-refuse"
    note = "The evidence retrieval layer failed uniformly across all sub-questions."
    event = {
        "event_id": "evt-note-low",
        "investigation_id": inv,
        "action_type": "note.emerged",
        "document_id": "doc-g",
        "payload": {
            "note_text": note,
            "note_id": "n-low",
            "source_event_ids": [],
            "confidence": "low",
        },
    }
    with (events / f"{inv}.jsonl").open("w") as f:
        f.write(json.dumps(event) + "\n")
    nid = promote_from_note_event(
        event,
        enabled=True,
        emit_graph_events=False,
        events_dir=str(events),
        min_groundedness=0.5,
    )
    assert nid is None
    con = duckdb.connect(db, read_only=True)
    n = con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
    con.close()
    assert n == 0


def test_promote_passage_aligned_note_clears_bar(tmp_path: Path, monkeypatch) -> None:
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _init_doc(db)
    inv = "inv-pass"
    note = (
        "Four score and seven years ago the fathers brought forth a new nation "
        "conceived in Liberty on this continent."
    )
    event = {
        "event_id": "evt-note-hi",
        "investigation_id": inv,
        "action_type": "note.emerged",
        "document_id": "doc-g",
        "payload": {
            "note_text": note,
            "note_id": "n-hi",
            "source_event_ids": [],
            "confidence": "high",
        },
    }
    with (events / f"{inv}.jsonl").open("w") as f:
        f.write(json.dumps(event) + "\n")
    nid = promote_from_note_event(
        event,
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
