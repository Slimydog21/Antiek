"""Read-only Hermes research-event ingest bridge.

These tests pin the contract of ``substrate/research_bridge/hermes_ingest.py``:
parse tolerance, investigation grouping, deterministic rendering, live-path
ingest via ``ingest_file``, content-addressed idempotency, and honest
skip/error statuses. No network is touched — the bridge performs no model
call at ingest time (distillation is the caller's separate async step).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import FrozenInstanceError

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.hermes_ingest import (
    HERMES_INGEST_VERSION,
    HermesIngestBatch,
    HermesIngestResult,
    group_investigations,
    ingest_hermes_events,
    ingest_hermes_investigation,
    iter_hermes_events,
    parse_hermes_event_line,
    render_investigation_text,
)


class _FakeEmbedding:
    dimension = 8

    def encode(self, text):
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev, "root": d}


def _event(
    event_id: str,
    investigation_id: str = "inv-1",
    *,
    emitted_at: str | None = "2026-07-01T00:00:00Z",
    phase: str = "research",
    role: str = "note_taker",
    action_type: str = "synthesize",
    payload: dict | None = None,
    schema_version: int = 31,
) -> dict:
    return {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "phase": phase,
        "role": role,
        "action_type": action_type,
        "emitted_at": emitted_at,
        "schema_version": schema_version,
        "payload": payload if payload is not None else {"text": "a finding"},
    }


def _write_events(env, events, filename="trace.jsonl"):
    path = os.path.join(env["events"], filename)
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    return path


# --------------------------------------------------------------------------
# parse tolerance
# --------------------------------------------------------------------------


def test_parse_valid_line_captures_fields():
    record = parse_hermes_event_line(json.dumps(_event("e1", schema_version=31)))
    assert record is not None
    assert record.event_id == "e1"
    assert record.investigation_id == "inv-1"
    assert record.schema_version == 31
    assert record.payload == {"text": "a finding"}


def test_parse_blank_line_returns_none():
    assert parse_hermes_event_line("   \n") is None
    assert parse_hermes_event_line("") is None


def test_parse_malformed_json_returns_none():
    assert parse_hermes_event_line("{not json") is None
    assert parse_hermes_event_line("[1, 2, 3]") is None


def test_parse_missing_required_keys_returns_none():
    no_event = {"investigation_id": "inv-1"}
    no_inv = {"event_id": "e1"}
    assert parse_hermes_event_line(json.dumps(no_event)) is None
    assert parse_hermes_event_line(json.dumps(no_inv)) is None


def test_parse_non_string_ids_returns_none():
    bad = {"event_id": 5, "investigation_id": "inv-1"}
    assert parse_hermes_event_line(json.dumps(bad)) is None


# --------------------------------------------------------------------------
# iteration + grouping
# --------------------------------------------------------------------------


def test_iter_skips_blank_and_malformed_lines(env):
    _write_events(env, [_event("e1"), _event("e2")])
    # Append a blank line and a malformed line to the same file.
    path = os.path.join(env["events"], "trace.jsonl")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n{broken\n")
    records = list(iter_hermes_events(env["events"]))
    assert [r.event_id for r in records] == ["e1", "e2"]


def test_iter_missing_dir_yields_nothing():
    assert list(iter_hermes_events("/nonexistent/hermes/dir")) == []


def test_group_two_investigations_sorted_by_time():
    events = [
        parse_hermes_event_line(json.dumps(_event("b2", "inv-2", emitted_at="2026-07-02T00:00:00Z"))),
        parse_hermes_event_line(json.dumps(_event("a1", "inv-1", emitted_at="2026-07-01T00:00:00Z"))),
        parse_hermes_event_line(json.dumps(_event("a0", "inv-1", emitted_at="2026-06-30T00:00:00Z"))),
    ]
    groups = group_investigations(events)
    assert set(groups) == {"inv-1", "inv-2"}
    inv1 = groups["inv-1"]
    assert [e.event_id for e in inv1.events] == ["a0", "a1"]  # chronological
    assert inv1.first_emitted_at == "2026-06-30T00:00:00Z"
    assert inv1.last_emitted_at == "2026-07-01T00:00:00Z"


def test_group_events_without_timestamp_sort_stably():
    events = [
        parse_hermes_event_line(json.dumps(_event("x1", emitted_at=None))),
        parse_hermes_event_line(json.dumps(_event("x2", emitted_at=None))),
    ]
    groups = group_investigations(events)
    assert [e.event_id for e in groups["inv-1"].events] == ["x1", "x2"]
    assert groups["inv-1"].first_emitted_at is None


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def test_render_is_deterministic_and_carries_provenance():
    inv = group_investigations(
        [parse_hermes_event_line(json.dumps(_event("e1")))]
    )["inv-1"]
    text_a = render_investigation_text(inv)
    text_b = render_investigation_text(inv)
    assert text_a == text_b
    assert "inv-1" in text_a
    assert "hermes" in text_a
    assert str(HERMES_INGEST_VERSION) in text_a
    assert "e1" in text_a
    assert text_a.strip() != ""


# --------------------------------------------------------------------------
# live-path ingest + idempotency
# --------------------------------------------------------------------------


def test_ingest_one_investigation_writes_new_document(env):
    _write_events(env, [_event("e1"), _event("e2", action_type="question")])
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        investigations = group_investigations(iter_hermes_events(env["events"]))
        result = ingest_hermes_investigation(con, investigations["inv-1"])
    finally:
        con.close()
    assert result.status == "ok"
    assert result.was_new is True
    assert result.document_id is not None
    assert result.events_count == 2
    assert result.source_label == "hermes:inv-1"

    con = connect_read(env["db"])
    try:
        count = con.execute(
            "SELECT count(*) FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert count == 1


def test_ingest_is_idempotent_cache_hit(env):
    _write_events(env, [_event("e1")])
    investigations = group_investigations(iter_hermes_events(env["events"]))
    # First ingest.
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        first = ingest_hermes_investigation(con, investigations["inv-1"])
        second = ingest_hermes_investigation(con, investigations["inv-1"])
    finally:
        con.close()
    assert first.status == "ok" and first.was_new is True
    assert second.status == "cache_hit" and second.was_new is False
    assert first.document_id == second.document_id

    con = connect_read(env["db"])
    try:
        count = con.execute(
            "SELECT count(*) FROM documents WHERE document_id = ?",
            [first.document_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert count == 1  # no duplicate document


def test_ingest_hermes_events_batch_rollup(env):
    # Two investigations, plus a malformed line that must be tolerated.
    events = [
        _event("a1", "inv-a"),
        _event("b1", "inv-b"),
        _event("a2", "inv-a", emitted_at="2026-07-02T00:00:00Z"),
    ]
    _write_events(env, events)
    with open(os.path.join(env["events"], "trace.jsonl"), "a", encoding="utf-8") as handle:
        handle.write("\n{malformed\n")
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        batch = ingest_hermes_events(con, env["events"])
    finally:
        con.close()
    assert isinstance(batch, HermesIngestBatch)
    assert batch.new_count == 2
    assert batch.cache_hit_count == 0
    assert batch.error_count == 0
    # Investigations processed in sorted-id order.
    assert [r.investigation_id for r in batch.results] == ["inv-a", "inv-b"]


def test_ingest_hermes_events_limit_caps_investigations(env):
    _write_events(
        env,
        [_event("a1", "inv-a"), _event("b1", "inv-b"), _event("c1", "inv-c")],
    )
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        batch = ingest_hermes_events(con, env["events"], limit=2)
    finally:
        con.close()
    assert len(batch.results) == 2
    assert batch.new_count == 2




# --------------------------------------------------------------------------
# regression: honest malformed counting + corrupt-UTF8 tolerance
# (caught by glm-codex adversarial review)
# --------------------------------------------------------------------------


def test_batch_counts_malformed_lines_honestly(env):
    _write_events(env, [_event("a1", "inv-a")])
    path = os.path.join(env["events"], "trace.jsonl")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("{not json\n")  # bad JSON
        handle.write('{"event_id": "x"}\n')  # missing investigation_id
        handle.write('{"investigation_id": "y"}\n')  # missing event_id
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        batch = ingest_hermes_events(con, env["events"])
    finally:
        con.close()
    assert batch.malformed_lines == 3
    assert batch.new_count == 1
    assert batch.error_count == 0


def test_invalid_utf8_does_not_abort_sweep(env):
    _write_events(env, [_event("a1", "inv-a")])
    bad_path = os.path.join(env["events"], "corrupt.jsonl")
    with open(bad_path, "wb") as handle:
        handle.write(b"\xff\xfe not valid utf-8\n")
    # Must not raise — a corrupted file must not abort the whole sweep.
    con = connect_write(env["db"], purpose="hermes_ingest")
    try:
        batch = ingest_hermes_events(con, env["events"])
    finally:
        con.close()
    # The valid investigation from the good file is still ingested.
    assert batch.new_count == 1
    # The corrupted line surfaces as a malformed count, never a crash.
    assert batch.malformed_lines >= 1


def test_result_is_frozen_dataclass():
    result = HermesIngestResult(
        investigation_id="inv-1",
        document_id=None,
        status="skipped_empty",
        events_count=0,
        was_new=False,
        source_label="hermes:inv-1",
        document_type=None,
    )
    with pytest.raises(FrozenInstanceError):
        result.status = "ok"  # type: ignore[misc]
