"""Passage-aligned note groundedness: broadened evidence + backfill honesty."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from roles.note_taker.prompt import NOTE_TAKER_SYSTEM_PROMPT
from roles.note_taker.replay import CONSUMER_VERSION
from substrate.eval.groundedness import score_claim
from substrate.graph.insight_question import (
    _note_evidence_texts,
    _score_note_groundedness,
    rescore_promoted_note_groundedness,
)


def test_prompt_requires_document_entailment() -> None:
    assert "Entail the document" in NOTE_TAKER_SYSTEM_PROMPT
    assert "Passage-aligned lexicon" in NOTE_TAKER_SYSTEM_PROMPT
    assert CONSUMER_VERSION >= 3


def test_note_evidence_includes_decompose_agenda(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    inv = "inv-test-evid"
    rows = [
        {
            "event_id": "evt-dec",
            "investigation_id": inv,
            "action_type": "decompose.delivered",
            "payload": {
                "decomposition": [
                    {
                        "sub_question": "When was the Gettysburg Address delivered?",
                        "rationale": "Date anchors public-domain analysis.",
                    }
                ]
            },
        },
        {
            "event_id": "evt-ev",
            "investigation_id": inv,
            "action_type": "evidence.retrieve.delivered",
            "payload": {
                "sub_question": "When was the Gettysburg Address delivered?",
                "answer": "November 19, 1863 per the page label.",
            },
        },
        {
            "event_id": "evt-note",
            "investigation_id": inv,
            "action_type": "note.emerged",
            "document_id": "doc-g",
            "payload": {
                "note_text": "The Gettysburg Address was delivered November 19, 1863.",
                "source_event_ids": ["evt-ev"],
            },
        },
    ]
    with (events / f"{inv}.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    texts = _note_evidence_texts(rows[-1], events_dir=str(events), con=None)
    blob = "\n".join(texts)
    assert "November 19, 1863" in blob
    assert "When was the Gettysburg Address delivered?" in blob


def test_passage_aligned_note_clears_threshold_with_chunks(tmp_path: Path) -> None:
    db = str(tmp_path / "g.duckdb")
    con = duckdb.connect(db)
    con.execute(
        "CREATE TABLE chunks (chunk_id VARCHAR, document_id VARCHAR, text VARCHAR)"
    )
    passage = (
        "Four score and seven years ago our fathers brought forth on this "
        "continent a new nation, conceived in Liberty, and dedicated to the "
        "proposition that all men are created equal."
    )
    con.execute(
        "INSERT INTO chunks VALUES ('c1', 'doc-g', ?)",
        [passage],
    )
    note = (
        "Lincoln's Gettysburg Address opens by recalling that four score and "
        "seven years ago the nation was conceived in liberty and dedicated to "
        "the proposition that all men are created equal."
    )
    event = {
        "event_id": "evt-note",
        "investigation_id": "inv-x",
        "action_type": "note.emerged",
        "document_id": "doc-g",
        "payload": {"note_text": note, "source_event_ids": []},
    }
    # empty events dir — chunks alone should entail the passage-aligned note
    (tmp_path / "ev").mkdir()
    evid = _note_evidence_texts(event, events_dir=str(tmp_path / "ev"), con=con)
    score = _score_note_groundedness(con, note, chunk_id="c1", evidence_texts=evid)
    assert score >= 0.5, score
    # process-meta note should stay low against the same chunk
    meta = "The evidence retrieval layer failed uniformly across all sub-questions."
    meta_score = float(score_claim(meta, [passage], cited_chunk_ids=["c1"]).score)
    assert meta_score < 0.5, meta_score
    con.close()


def test_rescore_backfill_updates_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    inv = "inv-bf"
    note = (
        "Four score and seven years ago the fathers brought forth a new nation "
        "conceived in liberty."
    )
    passage = (
        "Four score and seven years ago our fathers brought forth on this "
        "continent a new nation, conceived in Liberty."
    )
    con = duckdb.connect(db)
    con.execute(
        "CREATE TABLE chunks (chunk_id VARCHAR, document_id VARCHAR, text VARCHAR)"
    )
    con.execute("INSERT INTO chunks VALUES ('c1', 'doc-g', ?)", [passage])
    con.execute(
        "CREATE TABLE nodes ("
        "node_id VARCHAR, canonical_label VARCHAR, node_type VARCHAR, "
        "metadata VARCHAR, embedding DOUBLE[], graph_scope VARCHAR, "
        "created_at TIMESTAMP, degree_cached INTEGER, owner_user_id VARCHAR)"
    )
    # Under-score stored (simulates pre-broaden deposit)
    meta = {
        "source_document_id": "doc-g",
        "chunk_id": "c1",
        "investigation_id": inv,
        "origin_event_id": "evt-note",
        "groundedness_score": 0.1,
    }
    con.execute(
        "INSERT INTO nodes VALUES (?, ?, 'insight', ?, NULL, 'personal', CURRENT_TIMESTAMP, 0, NULL)",
        ["insight-bf1", note, json.dumps(meta)],
    )
    con.close()

    with (events / f"{inv}.jsonl").open("w") as f:
        f.write(
            json.dumps(
                {
                    "event_id": "evt-note",
                    "investigation_id": inv,
                    "action_type": "note.emerged",
                    "document_id": "doc-g",
                    "payload": {"note_text": note, "source_event_ids": []},
                }
            )
            + "\n"
        )

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    rows = rescore_promoted_note_groundedness(
        db_path=db,
        events_dir=str(events),
        source_document_id="doc-g",
        dry_run=False,
    )
    assert len(rows) == 1
    assert rows[0]["new"] >= 0.5
    assert rows[0]["updated"] is True
    con = duckdb.connect(db, read_only=True)
    stored = json.loads(
        con.execute(
            "SELECT metadata FROM nodes WHERE node_id='insight-bf1'"
        ).fetchone()[0]
    )
    assert float(stored["groundedness_score"]) >= 0.5
    con.close()
